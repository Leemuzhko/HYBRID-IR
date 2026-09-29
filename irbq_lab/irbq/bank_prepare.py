"""Non-destructive authoring -> runtime preparation, independent of ZDL offsets."""
import copy
from dataclasses import dataclass, replace
import numpy as np
from .dsp import Model, prepare, frequency_grid, response_metrics


class ConversionRequired(ValueError):
    pass


@dataclass(frozen=True)
class TargetModel:
    fs: int = 44100
    max_fir: int = 4096
    supports_bq: bool = True
    trained_reso: bool = True


def export_snapshot(project, *, include_source=False):
    """Snapshot models/recipes, not unused authoring arrays or WAV containers.

    Original-mode workers borrow read-only views while the GUI edit gate is held.
    They never mutate those views. Completed PatchPlans contain no source arrays.
    """
    from .project import Session
    slots=[]
    for slot in project.slots:
        model=slot.model.clone()
        session=None
        if include_source and slot.session is not None:
            source=slot.session.source
            if source is not None:
                source=np.asarray(source).view();source.flags.writeable=False
            session=Session(source=source,source_fs=slot.session.source_fs,
                source_name=slot.session.source_name,config=copy.deepcopy(slot.session.config),model=model)
        slots.append(replace(slot,model=model,session=session))
    return replace(project,slots=slots)


def preview_bank(project,target,*,mode='preserve',taps=None):
    """Conservative storage preview; never preprocess audio or evaluate responses."""
    if mode=='preserve':return project
    if mode not in ('bake','original') or type(taps) is not int or not 32<=taps<=target.max_fir:
        raise ValueError('Choose a supported conversion mode and FIR length')
    slots=[]
    for i,slot in enumerate(project.slots):
        if mode=='original' and (slot.session is None or slot.session.source is None):
            raise ConversionRequired('Original IR is unavailable for slot '+slot.label)
        # Distinct coefficient payloads give an upper bound before deduplication.
        fir=np.zeros(taps);fir[:2]=[.25,.001*(i+1)]
        slots.append(replace(slot,model=Model(target.fs,fir,[]),session=None))
    return replace(project,slots=slots)


def conversion_metrics(reference,converted):
    f=frequency_grid(reference.fs,2048)
    if reference.fir_enabled and not reference.sections and len(reference.fir)>8192:
        from scipy import fft
        from .dsp import quantize_fir
        q,scale=quantize_fir(reference.fir)
        n=fft.next_fast_len(len(q))
        bins=np.unique(np.rint(f*n/reference.fs).astype(int))
        f=bins*reference.fs/n
        # Exact sampled polynomial on FFT bins: no sparse-grid interpolation.
        response=fft.rfft(q.astype(float)/32768*scale,n)[bins]*10**(reference.output_gain_db/20)
        grid=dict(method='exact FFT bins for long FIR reference; no interpolation',
                  fs=reference.fs,fft_size=n,bins=bins.tolist())
    else:
        response=reference.response(f,True)
        grid=dict(method='direct frequency evaluation',fs=reference.fs,
                  spacing='geomspace',count=len(f),first_hz=float(f[0]),last_hz=float(f[-1]))
    return response_metrics(response,converted.response(f,True),f,reference.fs),grid


def prepare_bank(project, target=TargetModel(), *, mode='preserve', taps=None):
    """Return a private export copy and measured conversion report.

    preserve: exact saved model; bake: current quantized FIR+BQ+nominal RESO+gain;
    original: rerun saved preparation on full original samples (never fit anew).
    Only the latter two require explicit UI/CLI selection and a length.
    """
    if mode not in ('preserve','bake','original'):raise ValueError('Unknown preparation mode')
    if mode!='preserve' and (type(taps) is not int or not 32<=taps<=target.max_fir):
        raise ValueError('Choose a supported FIR length (32..%d)' % target.max_fir)
    result=export_snapshot(project)
    rows=[]
    for source,slot in zip(project.slots,result.slots):
        model=source.model
        from .zoom_bank import validate_model
        validate_model(model)
        if model.fs!=target.fs:raise ConversionRequired('Model sample rate is incompatible with template')
        if any(b.control_role not in ('','reso') for b in model.sections):
            raise ValueError('Unsupported control role; cannot silently discard it')
        if mode=='preserve':
            if (not target.supports_bq and model.sections) or (not target.trained_reso and any(b.control_role for b in model.sections)):
                raise ConversionRequired('Template cannot preserve these BQ roles; explicitly bake the current model into FIR')
            if model.fir_enabled and len(model.fir)>target.max_fir:
                raise ConversionRequired('FIR exceeds template length; explicitly choose conversion/truncation')
            rows.append(dict(slot=slot.uid,mode=mode,source_available=bool(source.session is not None and source.session.source is not None)))
            continue
        if mode=='bake':
            # Coefficient quantization matches the bank encoder, not C674 arithmetic.
            impulse=model.render(length=taps,quantized=True)
            reference=model
        else:
            session=source.session
            if session is None or session.source is None:
                raise ConversionRequired('Original IR is unavailable for slot '+slot.label)
            cfg=copy.deepcopy(session.config)
            if cfg.fs!=target.fs:raise ValueError('Saved preparation rate differs from template')
            prepared,_,_=prepare(session.source,session.source_fs,cfg)
            reference=Model(target.fs,prepared,[])
            impulse=np.pad(prepared[:taps],(0,max(0,taps-len(prepared))))
        if not np.all(np.isfinite(impulse)):raise ValueError('Non-finite rendered FIR')
        # Gain is already in impulse. Roles are deliberately baked at nominal values.
        slot.model=Model(target.fs,np.asarray(impulse),[],name=model.name,
                         notes='Export derivative; original authoring model is unchanged',output_gain_db=0.)
        metrics,grid=conversion_metrics(reference,slot.model)
        rows.append(dict(slot=slot.uid,mode=mode,taps=taps,metrics=metrics,
                         response_method=grid['method'],response_grid=grid,
                         nominal_controls_baked=mode=='bake',gain_baked=True,
                         comparison='quantized coefficients, host float64; not pedal arithmetic'))
    return result,dict(schema='hybrid-bank-preparation/1',mode=mode,slots=rows,
                       source_project_modified=False,hardware_validated=False)
