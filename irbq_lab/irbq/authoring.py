"""Portable authoring data. No ZDL decoding, fitting or DSP transformations."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import os
from pathlib import Path
from dataclasses import asdict, dataclass
import zipfile
import numpy as np
from .dsp import Model, PrepConfig
from .project import Session, import_models

MAX_FILE = 64_000_000
MAX_EXPANDED = 256_000_000


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')


def archive(raw, limit=MAX_EXPANDED):
    if len(raw) > MAX_FILE:
        raise ValueError('Project file is too large')
    result = zipfile.ZipFile(io.BytesIO(raw))
    items = result.infolist()
    if len(items) > 64 or len({i.filename for i in items}) != len(items) or sum(i.file_size for i in items) > limit:
        result.close()
        raise ValueError('Project archive exceeds safe limits')
    return result


def read_file(path):
    path = Path(path)
    if path.stat().st_size > MAX_FILE:
        raise ValueError('Project file is too large')
    return path.read_bytes()


def session_bytes(session):
    if session.model is None:
        raise ValueError('No model to save')
    signals = {}
    for key in ('source', 'target', 'before_mpt'):
        value = getattr(session, key)
        if value is not None:
            signals[key] = np.asarray(value, dtype=np.float64)
    metadata = dict(schema='irbq-project/2', source_name=session.source_name,
                    source_fs=session.source_fs, prep=asdict(session.config), log=session.log,
                    model=session.model.to_dict(), snapshots=[m.to_dict() for m in session.snapshots])
    data = io.BytesIO()
    np.savez_compressed(data, **signals)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('project.json', json_bytes(metadata))
        z.writestr('signals.npz', data.getvalue())
    raw = output.getvalue()
    session_from_bytes(raw)  # Validate the exact representation before publication.
    return raw


def session_from_bytes(raw,max_signal_bytes=128_000_000):
    with archive(raw, 160_000_000) as z:
        d = json.loads(z.read('project.json'))
        if d.get('schema') not in ('irbq-project/1', 'irbq-project/2'):
            raise ValueError('Unsupported IRBQ project version')
        payload = z.read('signals.npz')
    with archive(payload, 160_000_000) as nested:
        # Validate NPY declarations before allocation, including malicious short payloads.
        expanded=0
        for item in nested.infolist():
            if item.filename not in ('source.npy','target.npy','before_mpt.npy'):
                raise ValueError('Unexpected project signal')
            with nested.open(item) as handle:
                version=np.lib.format.read_magic(handle)
                if version==(1,0):shape,_,dtype=np.lib.format.read_array_header_1_0(handle)
                elif version==(2,0):shape,_,dtype=np.lib.format.read_array_header_2_0(handle)
                else:raise ValueError('Unsupported signal array version')
                count=1
                for n in shape:
                    if n<0 or n>6_000_000:raise ValueError('Invalid signal dimensions')
                    count*=n
                if dtype.kind not in 'fiu' or count>6_000_000 or count*dtype.itemsize!=item.file_size-handle.tell():
                    raise ValueError('Unsafe signal array')
                expanded+=count*8  # Stored signals are materialized as float64.
                if expanded>max_signal_bytes:raise ValueError('Project signals exceed memory budget')
    signals = {}
    with np.load(io.BytesIO(payload), allow_pickle=False) as values:
        for key in ('source', 'target', 'before_mpt'):
            if key not in values:
                signals[key] = None
                continue
            value = values[key]
            if value.dtype.kind not in 'fiu' or not np.all(np.isfinite(value)):
                raise ValueError('Invalid project signal')
            if key == 'source':
                if value.ndim not in (1, 2) or value.size > 6_000_000 or (value.ndim == 2 and value.shape[1] > 8):
                    raise ValueError('Invalid source signal')
            elif value.ndim != 1 or value.size > 4_000_000:
                raise ValueError('Invalid reference signal')
            signals[key] = value.astype(np.float64, copy=True)
    cfg = PrepConfig(**{k: v for k, v in d['prep'].items() if k in PrepConfig.__dataclass_fields__})
    model = Model.from_dict(d['model'])
    if len(d.get('snapshots',[]))>128:raise ValueError('Too many snapshots')
    snapshots = [Model.from_dict(m) for m in d.get('snapshots', [])]
    if len(snapshots) > 128 or cfg.fs != model.fs or any(m.fs != cfg.fs for m in snapshots):
        raise ValueError('Incompatible project models')
    source_fs = int(d['source_fs'])
    if not 8000 <= source_fs <= 192000:
        raise ValueError('Invalid source sample rate')
    return Session(signals['source'], source_fs, d.get('source_name', ''), signals['target'],
                   signals['before_mpt'], cfg, d.get('log', []), model, snapshots)


def model_session(model):
    return Session(source_fs=model.fs, config=PrepConfig(fs=model.fs), model=model.clone())


def validate_card(raw):
    from PIL import Image
    if len(raw)>2_000_000:raise ValueError('Card image is too large')
    with Image.open(io.BytesIO(raw)) as image:
        if image.format!='PNG' or image.size!=(128,64):raise ValueError('Bank card must be a 128x64 PNG')
        image.load()


def portable_bank_bytes(project):
    project.validate(allow_empty=True)
    output = io.BytesIO()
    slots = []
    signal_bytes=0
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for i, slot in enumerate(project.slots):
            session = copy.deepcopy(slot.session) if slot.session is not None else model_session(slot.model)
            session.model = slot.model.clone()
            signal_bytes+=sum(np.asarray(v).size*8 for v in (session.source,session.target,session.before_mpt) if v is not None)
            if signal_bytes>128_000_000:raise ValueError('Bank signals exceed memory budget')
            name = f'sessions/{i}.irbq'
            z.writestr(name, session_bytes(session))
            slots.append(dict(label=slot.label, uid=slot.uid, session=name))
        image = read_file(project.image)
        validate_card(image)
        z.writestr('card.png', image)
        z.writestr('bank.json', json_bytes(dict(schema='hybrid-ir-bank/1', name=project.name,
            fxid=project.fxid, gid=project.gid, filename=project.filename, slots=slots)))
    raw = output.getvalue()
    with archive(raw):
        pass
    return raw


def load_portable_bank(path):
    from .zoom_bank import BankProject, Slot, atomic_write
    from .preferences import settings_path
    with archive(read_file(path)) as z:
        data = json.loads(z.read('bank.json'))
        if data.pop('schema', None) != 'hybrid-ir-bank/1':
            raise ValueError('Unsupported portable bank version')
        descriptors = data.pop('slots')
        if set(data)!={'name','fxid','gid','filename'}:
            raise ValueError('Unexpected portable bank metadata; local paths are prohibited')
        if len(descriptors) > 8:
            raise ValueError('Too many bank slots')
        slots = []
        remaining=128_000_000
        for i, descriptor in enumerate(descriptors):
            if descriptor['session'] != f'sessions/{i}.irbq':
                raise ValueError('Invalid bank session reference')
            session = session_from_bytes(z.read(descriptor['session']),remaining)
            remaining-=sum(v.nbytes for v in (session.source,session.target,session.before_mpt) if v is not None)
            slots.append(Slot(descriptor['label'], session.model.clone(), session, descriptor['uid']))
        image = z.read('card.png')
    validate_card(image)
    project = BankProject(**data, slots=slots,stock_folder='',patched_folder='')
    project.validate(allow_empty=True)
    # Embedded image is materialized in an application-owned, content-addressed cache.
    cache = settings_path().parent / 'bank_cards'
    for parent in (cache,*cache.parents):
        if parent.is_symlink() or (hasattr(parent,'is_junction') and parent.is_junction()):
            raise ValueError('Unsafe card cache')
    cache.mkdir(parents=True, exist_ok=True)
    card = cache / (hashlib.sha256(image).hexdigest() + '.png')
    if card.exists():
        if card.is_symlink() or card.read_bytes() != image:
            raise ValueError('Card cache integrity mismatch')
    else:
        atomic_write(card, image)
    project.image = str(card)
    return project


def default_library_path():
    override = os.environ.get('IRBQ_SETTINGS_PATH')
    if override:
        return Path(override).parent / 'Library'
    return Path.home() / 'Documents' / 'HYBRID IR' / 'Library'


@dataclass
class LibraryEntry:
    path: Path
    session: Session

    @property
    def kind(self):
        model = self.session.model
        return 'Hybrid' if model.fir_enabled and model.sections else ('FIR' if model.fir_enabled else 'BQ')


def library_session(path):
    path = Path(path)
    if path.suffix.lower() == '.irbq':
        return Session.load(path)
    models = import_models(path)
    if len(models) != 1:
        raise ValueError('Library imports require a single model per file')
    return model_session(models[0])


def scan_library(folder,check_cancel=None):
    folder = Path(folder)
    entries, errors = [], []
    candidates=[];visited=0
    for parent,dirs,files in os.walk(folder,followlinks=False):
        if check_cancel:check_cancel()
        dirs[:]=[d for d in dirs if not (Path(parent)/d).is_symlink()
                 and not (hasattr(Path,'is_junction') and (Path(parent)/d).is_junction())]
        visited+=len(dirs)+len(files)
        if visited>10000:raise ValueError('Library scan limited to 10000 filesystem entries')
        for name in files:
            path=Path(parent)/name
            if not path.is_symlink() and (path.suffix.lower()=='.irbq' or path.name.lower()=='model.json'):candidates.append(path)
        if len(candidates)>1000:raise ValueError('Library scan limited to 1000 project/model files')
    retained=0
    for path in sorted(candidates):
        if check_cancel:check_cancel()
        try:
            session=library_session(path)
            from .zoom_rbj_bank import bq_count
            bq_count(session.model)  # Reject invalid roles before a Tk filter renders them.
            size=sum(v.nbytes for v in (session.source,session.target,session.before_mpt) if v is not None)
            if retained+size>256_000_000:raise ValueError('Library reference memory budget exceeded')
            retained+=size
            entries.append(LibraryEntry(path,session))
        except (ValueError, OSError, KeyError, TypeError, AttributeError, IndexError, RuntimeError, OverflowError, EOFError, zipfile.BadZipFile) as exc:
            errors.append((path, str(exc)))
    return entries, errors
