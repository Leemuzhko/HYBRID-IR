"""Zoom bank authoring, separate from generic fitting. Always rebuild relocations."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import uuid
import numpy as np
from .dsp import Model, Biquad, quantize_fir, sos_array, sos_stability

SCHEMA = 'irbq-zoom-bank/1'
SDK = Path(__file__).resolve().parents[2] / 'hybridir_sdk'
TEMPLATE = SDK / 'src/custom/hybridir'
IDENTITY = [1., 0., 0., 0., 0.]
SOFT_CONST_BYTES = 22 * 1024  # warning, NOT a hardware maximum


def atomic_write(path, raw):
    """Publish on the same filesystem without exposing a partially written file."""
    path=Path(path)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.hybridir-',delete=False) as stream:
            temporary=Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()


def ascii_label(value, maximum=7):
    if not isinstance(value, str) or not value or not value.isascii():
        raise ValueError('Label must be non-empty ASCII')
    if len(value) > maximum or any(ord(c) < 32 or ord(c) > 126 for c in value):
        raise ValueError(f'Label must contain 1..{maximum} printable ASCII characters')
    return value


def import_irbq_package(path):
    """Only the explicit Trainer contract; never guess legacy gain/role semantics."""
    path=Path(path)
    if path.stat().st_size>64_000_000:raise ValueError('Model package too large')
    payload=json.loads(path.read_text(encoding='utf-8-sig'))
    if payload.get('schema')!='irbq-model/1':
        raise ValueError('Zoom import requires an IRBQ Trainer model.json export (irbq-model/1)')
    if payload.get('coefficient_order')!=['b0','b1','b2','a0','a1','a2']:
        raise ValueError('Unsupported or missing SOS coefficient order')
    model=Model.from_dict(payload['model'])
    validate_model(model)
    q,scale=quantize_fir(model.fir)
    if payload.get('rate')!=model.fs or payload.get('taps')!=len(model.fir):
        raise ValueError('Package rate/taps disagree with the model')
    expected=sos_array(model.sections,model.fs,True)
    sos=np.asarray(payload.get('sos'),dtype=float).reshape(-1,6)
    if not np.array_equal(sos,expected):raise ValueError('Package SOS disagree with the model')
    if payload.get('fir_q15')!=q.tolist() or payload.get('fir_gain')!=scale:
        raise ValueError('Package FIR Q15/scale disagree with the model')
    return model


@dataclass
class Slot:
    label: str
    model: Model
    session: object = None
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class BankProject:
    name: str = 'HYBRID IR'
    fxid: int = 565
    gid: int = 2
    filename: str = 'HYBRIDIR'
    slots: list[Slot] = field(default_factory=list)
    image: str = str(TEMPLATE / 'IR_CAB.png')
    stock_folder: str = ''
    patched_folder: str = ''

    def validate(self, allow_empty=False):
        ascii_label(self.name, 12)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,8}', self.filename):
            raise ValueError('Filename must be 1..8 ASCII letters, digits, _ or -')
        if type(self.fxid) is not int or not 0 <= self.fxid <= 65535 or self.gid != 2:
            raise ValueError('Cabinet requires gid=2 and a uint16 ID')
        if not (0 if allow_empty else 1) <= len(self.slots) <= 8:
            raise ValueError('Compatibility envelope is 1..8 active slots; not a hardware guarantee')
        identifiers = [s.uid for s in self.slots]
        if len(set(identifiers)) != len(identifiers) or any(not re.fullmatch('[0-9a-f]{32}', s) for s in identifiers):
            raise ValueError('Invalid or duplicate bank slot identity')
        for slot in self.slots:
            ascii_label(slot.label)
            if slot.label == 'OFF':
                raise ValueError('OFF is reserved for bypass')
            validate_model(slot.model)

    def save(self, path):
        if Path(path).suffix.lower() == '.hybridbank':
            from .authoring import portable_bank_bytes
            atomic_write(path, portable_bank_bytes(self))
            return
        self.validate(allow_empty=True)
        path = Path(path)
        payload = dict(schema=SCHEMA, name=self.name, fxid=self.fxid, gid=self.gid,
                       filename=self.filename, image=self.image,
                       stock_folder=self.stock_folder, patched_folder=self.patched_folder,
                       slots=[dict(label=s.label, model=s.model.to_dict()) for s in self.slots])
        atomic_write(path,json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8'))

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.suffix.lower() == '.hybridbank':
            from .authoring import load_portable_bank
            return load_portable_bank(path)
        if path.stat().st_size > 64_000_000:
            raise ValueError('Bank project too large')
        p = json.loads(path.read_text(encoding='utf-8-sig'))
        if p.pop('schema', None) != SCHEMA:
            raise ValueError('Unsupported bank project version')
        p['slots'] = [Slot(s['label'], Model.from_dict(s['model'])) for s in p['slots']]
        result = cls(**p)
        result.validate(allow_empty=True)
        return result


def validate_model(model):
    if model.fs != 44100:
        raise ValueError('Zoom model must be prepared at 44100 Hz; BQ cannot be blindly resampled')
    h = np.asarray(model.fir, dtype=float)
    if h.ndim != 1 or not len(h) or not np.all(np.isfinite(h)):
        raise ValueError('FIR must be non-empty, mono and finite')
    if model.fir_enabled and not 32 <= len(h) <= 4096:
        raise ValueError('Active FIR authoring envelope is 32..4096 taps; prepare/pad shorter IR first')
    from .zoom_rbj_bank import bq_count
    bq_count(model)
    if not np.isfinite(model.output_gain_db) or abs(model.output_gain_db) > 60:
        raise ValueError('Overall Gain must be finite within +/-60 dB')
    sos = sos_array(model.sections, model.fs, True)
    if not np.all(np.isfinite(sos)) or sos_stability(sos) >= 1:
        raise ValueError('Quantized SOS must be finite and stable')
    scale = quantize_fir(h)[1] if model.fir_enabled else 1.
    if not np.isfinite(np.float32(scale)):
        raise ValueError('FIR scale overflows float32')


def catalog_entries(project):
    """Read wrapper IDs, not filenames. Invalid stock files fail closed."""
    catalog=json.loads(Path(__file__).with_name('stock_ids.json').read_text(encoding='utf-8'))
    if catalog.get('schema')!='hybridir-reserved-ids/1' or not catalog.get('entries'):
        raise ValueError('Missing or invalid bundled identity catalog')
    found = [dict(path='reserved:'+e['source'],gid=e['gid'],fxid=e['fxid'],
                  name=e['name'],reserved=True) for e in catalog['entries']]
    # stock_folder is retained only for loading older saved projects.
    for folder in (project.patched_folder,):
        if not folder:
            continue
        root = Path(folder)
        if not root.is_dir():
            raise ValueError(f'Catalog folder does not exist: {root}')
        for path in sorted(root.rglob('*')):
            if path.suffix.lower() != '.zdl':
                continue
            raw = path.read_bytes()
            if len(raw) < 76 or raw[:4] != b'\0\0\0\0' or raw[4:8] != b'SIZE' or raw[20:24] != b'INFO':
                raise ValueError(f'Invalid ZDL catalog entry: {path}')
            fxid = struct.unpack_from('<H', raw, 64)[0]
            gid = raw[60]
            name = None
            sys.path.insert(0,str(SDK/'build'))
            from zdl import Zdl
            from zdl_smoke import _section_map
            try:
                elf=Zdl.load(path).elf
                if elf[:4] != b'\x7fELF':raise ValueError('ELF payload absent')
                section=_section_map(elf)['.const']
                data=elf[section[4]:section[4]+section[5]]
                for marker in range(0,len(data)-96,4):
                    if data[marker:marker+6] != b'OnOff\0':continue
                    if struct.unpack_from('<I',data,marker+12)[0] != 1:continue
                    if struct.unpack_from('<I',data,marker+60)[0] != 0xFFFFFFFF:continue
                    value=data[marker+48:marker+60].split(b'\0',1)[0]
                    if value and all(32 <= c < 127 for c in value):name=value.decode('ascii')
                    break
            except (ValueError,KeyError,struct.error,IndexError) as exc:
                raise ValueError(f'Invalid ZDL catalog ELF: {path}: {exc}') from exc
            found.append(dict(path=str(path), gid=gid, fxid=fxid, name=name,reserved=False))
    return found


def identity_conflicts(project):
    conflicts=[e for e in catalog_entries(project)
               if (e['gid'],e['fxid']) == (project.gid,project.fxid)]
    if any(e.get('reserved') for e in conflicts):
        raise ValueError('ID reserved by the bundled catalog; choose a free ID')
    return [e['path'] for e in conflicts]


def suggest_free_id(project):
    occupied={e['fxid'] for e in catalog_entries(project) if e['gid']==project.gid}
    for fxid in list(range(max(1,project.fxid+1),65536))+list(range(1,max(1,project.fxid+1))):
        if fxid not in occupied:return fxid
    raise ValueError('No free ID in this category')


def _f(value):
    return f'{np.float32(value):.9e}f'


def _rows(rows):
    return ',\n'.join('{' + ','.join(_f(x) for x in row) + '}' for row in rows)


def pack_bank(project, capacity=None, binary=False):
    project.validate()
    if any(b.control_role for slot in project.slots for b in slot.model.sections):
        raise ValueError('Use the HVB4 role-aware patcher for models with RESO roles')
    models = [None] + [s.model for s in project.slots]
    fir_pool, bq_pool, desc = [], [], []
    fir_seen, bq_seen = {}, {}
    max_fir, max_bq = 32, 2
    # Preserve every imported section as exact correction; prepend two neutral
    # controls. Generic models are never guessed to have reserved role sections.
    for m in models:
        if m is not None and m.fir_enabled:
            q, scale = quantize_fir(m.fir)
            # Four-output ring and paired coefficient loads require 4-tap
            # alignment. Appending zeros preserves the FIR response exactly.
            if len(q) % 4:
                q = np.pad(q, (0, 4-len(q)%4))
            key = q.astype('<i2').tobytes()
            if key not in fir_seen:
                fir_seen[key] = len(fir_pool)
                fir_pool.extend(q.tolist())
            n, fi = len(q), fir_seen[key]
        else:
            n, fi, scale = 0, 0, 1.
        rows = np.array([IDENTITY, IDENTITY] + ([] if m is None else
                        sos_array(m.sections, 44100, True)[:, [0,1,2,4,5]].tolist()), dtype=np.float32)
        key = rows.astype('<f4').tobytes()
        if key not in bq_seen:
            bq_seen[key] = len(bq_pool)
            bq_pool.extend(rows.tolist())
        gain = 1. if m is None else 10 ** (m.output_gain_db / 20)
        desc.append([n, len(rows), 0, fi, bq_seen[key], scale, gain] + [0.] * 8)
        max_fir, max_bq = max(max_fir, n), max(max_bq, len(rows))
    # Empty FIR storage still requires one aligned dummy scalar in C.
    if not fir_pool:
        fir_pool = [0, 0]
    elif len(fir_pool) % 2:
        fir_pool.append(0)
    if len(fir_pool) > 65535 or len(bq_pool) > 65535:
        raise ValueError('Pool exceeds uint16 bank addressing')
    tables = []
    for kind, freq, q in [('Peak',110.,.7), ('HighShelf',3500.,.8)]:
        rows = [Biquad(kind=kind, f=freq, q=q, gain=db).coefficients(44100)[[0,1,2,4,5]]
                for db in np.linspace(-15,15,61)]
        table = np.array(rows, dtype=np.float32)
        for i in range(60):
            for frac in np.linspace(0,1,21):
                c = (table[i]*(1-frac)+table[i+1]*frac).astype(np.float32)
                if max(abs(np.roots([1.,c[3],c[4]]))) >= 1:
                    raise ValueError('Unstable interpolated control table')
        tables.append(table)
    count = len(models)
    labels = ['OFF'] + [s.label for s in project.slots]
    if capacity is not None:
        for key in ('entry_count', 'max_fir', 'max_bq', 'fir_pool_samples', 'bq_pool_sections'):
            if type(capacity.get(key)) is not int or capacity[key] <= 0:
                raise ValueError('Invalid template capacity: '+key)
        actual = (count, max_fir, max_bq, len(fir_pool), len(bq_pool))
        limits = tuple(capacity[k] for k in ('entry_count','max_fir','max_bq','fir_pool_samples','bq_pool_sections'))
        if any(a > b for a,b in zip(actual,limits)):
            raise ValueError(f'Bank exceeds template capacity: required {actual}, available {limits}')
        count,max_fir,max_bq,fir_size,bq_size = limits
        if count > 9 or max_fir > 4096 or max_fir % 4 or max_bq > 32 or fir_size > 65534 or fir_size % 2 or bq_size > 65535:
            raise ValueError('Unsupported template capacity')
        while len(desc) < count:
            desc.append(list(desc[0])); labels.append('EMPTY')
        fir_pool.extend([0] * (fir_size-len(fir_pool)))
        bq_pool.extend([IDENTITY] * (bq_size-len(bq_pool)))
    bank_bytes = 32 + 48*count + 8*count + 2*len(fir_pool) + 20*len(bq_pool) + 244 + 2440
    original = (TEMPLATE / 'generated/bank_u1.h').read_text()
    declaration = original.split('const GjBankBlob gj_bank = {')[0]
    values = dict(GJ_BANK_ENTRY_COUNT=count, GJ_BANK_MAX_FIR=max_fir,
                  GJ_BANK_MAX_BQ=max_bq, GJ_BANK_FIR_SAMPLES=len(fir_pool),
                  GJ_BANK_BQ_SECTIONS=len(bq_pool), GJ_BANK_DEPTH_TABLES=1, GJ_BANK_PRES_TABLES=1)
    for key, value in values.items():
        declaration = re.sub(r'(#define '+key+r' )\d+u', r'\g<1>'+str(value)+'u', declaration)
    lines = [declaration, 'const GjBankBlob gj_bank = {',
             '{0x32425249u,1,32,'+f'{count},{max_fir},{max_bq},8,1,{len(fir_pool)},{len(bq_pool)},48,61,{bank_bytes},0'+'},', '{']
    for d in desc:
        lines.append('{'+','.join(str(x) for x in d[:5])+','+','.join(_f(x) for x in d[5:])+'},')
    lines += ['}, {']
    for label in labels:
        lines.append('{'+','.join(str(b) for b in label.encode('ascii'))+',0},')
    lines += ['}, {'+','.join(str(x) for x in fir_pool)+'}, {', _rows(bq_pool), '}, {',
              ','.join(_f(10**(db/40)) for db in np.linspace(-15,15,61)), '}, {{',
              _rows(tables[0]), '}}, {{', _rows(tables[1]), '}}\n};\n#endif\n']
    # Use the real RLE length, descriptor layout and section alignment.
    from .zoom_budget import const_bytes, picture_bytes
    estimated_const = const_bytes(bank_bytes, len(picture_bytes(project.image)))
    report = dict(schema='hybridir-bank-report/1', bank_bytes=bank_bytes,
                  active_slots=len(project.slots), entry_count=count, max_fir=max_fir, max_bq=max_bq,
                  fir_pool_samples=len(fir_pool), bq_pool_sections=len(bq_pool),
                  estimated_const_bytes=estimated_const, soft_const_budget=SOFT_CONST_BYTES,
                  estimated_state_bytes=8+2*(4*max_fir+132+8*max_bq),
                  warnings=['Hardware slot count not validated', 'Cost is not measured CPU percent'] +
                  (['Estimated .const exceeds conservative 22 KiB soft budget'] if estimated_const > SOFT_CONST_BYTES else []),
                  roles=['RESO','PRES','exact imported correction sections'],
                  labels=labels)
    if binary:
        data = bytearray(struct.pack('<IHHHHBBHHHHHII', 0x32425249,1,32,count,max_fir,max_bq,8,1,
                                     len(fir_pool),len(bq_pool),48,61,bank_bytes,0))
        for d in desc:
            data.extend(struct.pack('<HBBHH10f', *d))
        for label in labels:
            data.extend(label.encode('ascii').ljust(8,b'\0'))
        data.extend(np.asarray(fir_pool,dtype='<i2').tobytes())
        data.extend(np.asarray(bq_pool,dtype='<f4').tobytes())
        data.extend(np.asarray([10**(db/40) for db in np.linspace(-15,15,61)],dtype='<f4').tobytes())
        for table in tables:data.extend(table.astype('<f4').tobytes())
        if len(data) != bank_bytes:raise ValueError('Internal bank size mismatch')
        return bytes(data), report
    return '\n'.join(lines), report


def build_project(project, output, overwrite=False, allow_identity_replace=False, *, capacity=None):
    """Stage privately, validate, then publish a distinct rebuilt ZDL."""
    project.validate()
    conflicts = identity_conflicts(project)
    if conflicts and not allow_identity_replace:
        raise ValueError('ID occupied: '+', '.join(conflicts)+'; choose a free ID or explicit replacement workflow')
    if conflicts and any(e['name'] != project.name for e in catalog_entries(project)
                         if e['path'] in conflicts):
        raise ValueError('Occupied ID has a different/unknown name; choose a free ID')
    output = Path(output)
    target = output / (project.filename + '.zdl')
    if target.exists() and not overwrite:
        raise FileExistsError(str(target))
    source, report = pack_bank(project, capacity=capacity)
    output.mkdir(parents=True, exist_ok=True)
    sys.path[:0] = [str(SDK), str(SDK / 'build')]
    from sdk.runtime_setup import verify_runtime
    verify_runtime(SDK)
    from sdk.build_effect import build_effect
    from PIL import Image
    from screen_image import Canvas, encode_zoom_rle
    image = Image.open(project.image).convert('L')
    if image.size != (128,64) or not set(image.getdata()) <= {0,255}:
        raise ValueError('PNG must contain 128x64 black/white pixels')
    canvas = Canvas()
    # Same black=1 convention as the prototype builder, confirmed on pedal.
    canvas.pixels = [[int(image.getpixel((x,y)) == 0) for x in range(128)] for y in range(64)]
    with tempfile.TemporaryDirectory(prefix='hybridir-build-', dir=output) as temp:
        stage = Path(temp)/'effect'
        stage.mkdir()
        (stage/'generated').mkdir()
        for file in ('effect.c','core.h'):
            shutil.copy2(TEMPLATE/file, stage/file)
        shutil.copy2(TEMPLATE/'generated/kernel.h', stage/'generated/kernel.h')
        (stage/'generated/bank_u1.h').write_text(source)
        (stage/'card.rle').write_bytes(encode_zoom_rle(canvas))
        manifest = json.loads((TEMPLATE/'manifest.json').read_text())
        manifest.update(effect_name=project.name, output_basename=project.filename,
                        fxid=project.fxid, gid=project.gid)
        manifest['ui']['screen'] = 'card.rle'
        for i in (3,6):
            manifest['params'][i].update(max=len(project.slots), labels=report['labels'], default=1, audio_default=.01)
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2))
        result = build_effect(stage, SDK, output_dir=Path(temp)/'dist')
        raw = result.zdl_path.read_bytes()
        from zdl import Zdl
        from zdl_smoke import _section_map
        sections = _section_map(Zdl.load(result.zdl_path).elf)
        report['sections'] = {name:sections[name][5] for name in
                              ('.text','.const','.fardata','.rela.dyn')}
        if report['sections']['.const'] > SOFT_CONST_BYTES:
            report['warnings'].append('Actual .const exceeds conservative soft budget; hardware test required')
        report['sha256'] = hashlib.sha256(raw).hexdigest()
        report['zdl_bytes'] = len(raw)
        atomic_write(target,raw)
    atomic_write(output/(project.filename+'.build.json'),json.dumps(report,indent=2).encode('utf-8'))
    return target, report
