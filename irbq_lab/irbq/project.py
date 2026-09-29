"""Self-contained projects, lossless snapshots, legacy import and explicit runtime exports."""
from __future__ import annotations
import io
import json
import zipfile
import hashlib
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
import numpy as np
import soundfile as sf
from .dsp import *
from . import __version__


@dataclass
class Session:
    source: np.ndarray | None = None
    source_fs: int = 44100
    source_name: str = ''
    target: np.ndarray | None = None
    before_mpt: np.ndarray | None = None
    config: PrepConfig = field(default_factory=PrepConfig)
    log: list[str] = field(default_factory=list)
    model: Model | None = None
    snapshots: list[Model] = field(default_factory=list)
    # Optional byte-exact source container, independent of the prepared/model IR.
    source_audio: bytes | None = None

    def load_audio(self,path):
        from .source_audio import decode_source
        path=Path(path)
        if path.stat().st_size>32_000_000:raise ValueError('Source audio is too large')
        raw=path.read_bytes()
        source,rate,_=decode_source(raw)
        self.source,self.source_fs,self.source_audio=source,rate,raw
        self.source_name=Path(path).name
        self.target=None; self.before_mpt=None; self.model=None; self.snapshots=[]

    def preprocess(self):
        if self.source is None:
            raise ValueError('Сначала загрузите IR WAV.')
        self.target,self.before_mpt,self.log=prepare(self.source,self.source_fs,self.config)
        self.model=Model(self.config.fs,np.r_[1.,np.zeros(127)],preset_sections(8,False,self.config.fs),'128+8')
        self.snapshots=[]

    def save(self,path):
        from .authoring import session_bytes
        from .zoom_bank import atomic_write
        atomic_write(path, session_bytes(self))

    @classmethod
    def load(cls,path):
        from .authoring import read_file, session_from_bytes
        return session_from_bytes(read_file(path))


def model_from_runtime(d):
    fs=int(d.get('fs',d.get('rate',44100)))
    fir=d.get('fir')
    if fir is None:
        fir=np.asarray(d['fir_q15'],dtype=float)/32768*float(d.get('fir_gain',1))
    sections=[]
    roles=d.get('runtime_roles',[])
    p=np.asarray(d.get('parameters_log',[]),float).reshape(-1,3)
    for i,sos in enumerate(d.get('sos',[])):
        role=roles[i] if i<len(roles) else f'SOS {i+1}'
        if i<len(p):
            fr,q,g=np.exp(p[i,0]),np.exp(p[i,1]),p[i,2]
            kind='LowShelf' if role=='low_shelf' else 'Peak'
            b=Biquad(kind,role,float(fr),float(q),float(g),raw=list(sos))
            if kind=='LowShelf': b.qmax=1.;b.gmin=-60.;b.fmin=10.
        elif role=='presence':
            b=Biquad('HighShelf','Presence',3500,.8,0,locked=True,qmax=1.,raw=list(sos))
        else:
            b=Biquad('SOS',role,locked=True,raw=list(sos))
        sections.append(b)
    return Model(fs,array1(fir),sections,d.get('name',d.get('label','Imported')),notes='Импорт: точные SOS, включая float32 исходного runtime.')


def import_models(path):
    path=Path(path)
    if path.stat().st_size>64_000_000:
        raise ValueError('JSON слишком большой.')
    d=json.loads(path.read_text(encoding='utf-8-sig'))
    if d.get('schema')=='irbq-model/1':
        return [Model.from_dict(d['model'])]
    if 'sections' in d and 'fir' in d:
        return [Model.from_dict(d)]
    if 'models' in d and isinstance(d['models'],dict):
        return [model_from_runtime({**v,'rate':d.get('rate',44100)}) for v in d['models'].values()]
    if 'fir_q15' in d or ('fir' in d and 'sos' in d):
        return [model_from_runtime(d)]
    raise ValueError('JSON не является поддерживаемой моделью. Поддержаны IRBQ Lab / GJ64CMP model / runtime_models.')


def export_model(folder,session:Session):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    m=session.model
    if m is None or session.target is None:
        raise ValueError('Нет модели/эталона.')
    sos=sos_array(m.sections,m.fs)
    sq=sos.astype(np.float32).astype(float)
    if not np.all(np.isfinite(sq)):
        raise ValueError('BQ не представим в float32.')
    if sos_stability(sq)>=1:
        raise ValueError('После float32-квантования BQ нестабилен. Экспорт остановлен.')
    q,gain=quantize_fir(m.fir)
    f=frequency_grid(m.fs,8000)
    T=fir_response(session.target,f,m.fs)
    H=m.response(f); Hq=m.response(f,True)
    reports={'float64_vs_target':response_metrics(T,H,f,m.fs),
             'q15_float32_vs_target':response_metrics(T,Hq,f,m.fs),
             'quantization_vs_float64':response_metrics(H,Hq,f,m.fs),
             'max_pole_radius':sos_stability(sq), 'phase_diagnostic':phase_diagnostics(T,H,f,m.fs),
             'arithmetic_multiply_estimate':(len(m.fir) if m.fir_enabled else 0)+5*len(m.sections)+(1 if abs(m.output_gain_db)>1e-12 else 0),
             'fir_enabled':m.fir_enabled, 'output_gain_db':m.output_gain_db,
             'warning':'Arithmetic estimate is NOT C6745 cycles or DSP percentage.'}
    payload={'schema':'irbq-model/1','app_version':__version__,'model':m.to_dict(),
             'rate':m.fs,'taps':len(m.fir),'fir_q15':q.astype(int).tolist(),'fir_gain':gain,
             'sos':sq.tolist(),'coefficient_order':['b0','b1','b2','a0','a1','a2'],
             'equation':'y=b0*x+b1*x1+b2*x2-a1*y1-a2*y2; a0=1',
             'source_name':session.source_name,'preparation':asdict(session.config),
             'preparation_log':session.log,'report':reports}
    (folder/'model.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    sf.write(folder/'residual_fir.wav',m.fir,m.fs,subtype='FLOAT')
    sf.write(folder/'prepared_reference.wav',session.target,m.fs,subtype='FLOAT')
    rendered=m.render(quantized=True)
    if not np.all(np.isfinite(rendered)) or np.max(abs(rendered))>=np.finfo(np.float32).max:
        raise ValueError('Переполнение развёрнутого IR. Уменьшите усиления / исправьте SOS.')
    sf.write(folder/'rendered_hybrid_ir.wav',rendered,m.fs,subtype='FLOAT')
    np.save(folder/'fir_float64.npy',m.fir)
    q.astype('<i2').tofile(folder/'fir_q15_le.bin')
    sq.astype('<f4').tofile(folder/'sos_float32_le.bin')
    import csv
    with (folder/'bq_parameters.csv').open('w',newline='',encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=['section','kind','f0_Hz','Q_or_S','Gain_dB','enabled','locked','overall_gain_db','raw_json'])
        writer.writeheader()
        for b in m.sections:
            writer.writerow(dict(section=b.name,kind=b.kind,f0_Hz=b.f,Q_or_S=b.q,Gain_dB=b.gain,enabled=b.enabled,locked=b.locked,overall_gain_db=m.output_gain_db,raw_json=json.dumps(b.raw) if b.kind=='SOS' else ''))
    np.savetxt(folder/'sos.csv',sq,delimiter=',',header='b0,b1,b2,a0,a1,a2',comments='',fmt='%.17g')
    (folder/'overall_gain.txt').write_text(f'{m.output_gain_db:+.9f} dB\n{10 ** (m.output_gain_db/20):.12g} linear\n',encoding='ascii')
    mat=np.c_[f,db(T),db(H),db(Hq),db(H)-db(T),np.unwrap(np.angle(T))*180/np.pi,
              np.unwrap(np.angle(H))*180/np.pi,np.angle(H*np.conj(T))*180/np.pi]
    np.savetxt(folder/'responses.csv',mat,delimiter=',',comments='',fmt='%.12g',
               header='frequency_Hz,target_dB,model_dB,quantized_dB,delta_dB,target_phase_deg,model_phase_deg,phase_error_deg')
    ident=re.sub('[^A-Za-z0-9_]','_',m.name)
    if not ident or ident[0].isdigit(): ident='ir_'+ident
    header=['/* IRBQ Lab. Generic data export; NOT a self-contained Zoom ZDL. */','#pragma once','#include <stdint.h>',
            f'#define IRBQ_FS {m.fs}',f'#define IRBQ_TAPS {len(q)}',f'#define IRBQ_SECTIONS {len(sq)}',
            f'#define IRBQ_FIR_ENABLED {1 if m.fir_enabled else 0}',
            f'static const float irbq_output_gain = {10 ** (m.output_gain_db/20):.9e}f;',
            f'static const float irbq_output_gain_db = {m.output_gain_db:.9e}f;',
            f'static const float irbq_fir_gain = {gain:.9e}f;',
            f'static const int16_t irbq_fir_q15[{len(q)}] = {{']
    for i in range(0,len(q),12): header.append('    '+', '.join(map(str,q[i:i+12]))+',')
    header+=['};','/* SOS: b0,b1,b2,a1,a2. Feedback is subtracted. */',f'static const float irbq_sos[{max(1,len(sq))}][5] = {{']
    for row in (sq if len(sq) else np.array([IDENTITY])):
        header.append('    {'+', '.join(f'{v:.9e}f' for v in row[[0,1,2,4,5]])+'},')
    header+=['};','']
    (folder/'model_data.h').write_text('\n'.join(header),encoding='ascii')
    (folder/'README_EXPORT_RU.md').write_text('''# Экспорт IRBQ Lab

`residual_fir.wav` — сохранённый короткий FIR. Если `fir_enabled=false`, он сейчас BYPASS и файл хранится для последующего включения/дообучения.
Если FIR включён — применять его ВМЕСТЕ с SOS.
`rendered_hybrid_ir.wav` — развёрнутый отклик всей FIR+BQ цепи (Q15/float32 коэффициенты,
расчёт на ПК float64); нужен для конволвера/прослушивания, но не сохраняет экономию IIR.
Хвост рендера конечен: до 8 секунд / оценка по радиусу полюсов, это не бесконечный IIR.
`prepared_reference.wav` — целевой IR после выбранной подготовки.
Все WAV float32, без индивидуальной нормализации. Коэффициенты могут быть >1.

`model_data.h` — данные общего назначения, НЕ готовый ZDL.
FIR: `q15 / 32768 * irbq_fir_gain`. После FIR+BQ применяется `irbq_output_gain` (Overall Gain). SOS: `b0,b1,b2,a1,a2`, обратная связь ВЫЧИТАЕТСЯ.
JSON содержит полные параметры, точные FIR, SOS, роли, ограничения, измеренные метрики.
Для IRDUAL4/GJ64CMP нужен отдельный адаптер банка, контроль ID/state/размера ZDL,
контроль runtime-индексов Resonance/Presence и реальная TI-сборка.

АЧХ — в dB относительно одного подготовленного эталона. Фаза не выравнивается в 1 kHz.
Диагностический detrend в отчёте НЕ означает физическую фазовую коррекцию.
Q15/float32 здесь — округление КОЭФФИЦИЕНТОВ, не побитная эмуляция арифметики C6745.
''',encoding='utf-8')
    sums=[]
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.name!='SHA256SUMS.txt':
            sums.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name)
    (folder/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='ascii')
    return reports
