"""DSP reference implementation. Float64 authoring; no implicit level/phase alignment.
RBJ formula references are listed in docs/THEORY_RU.md.
"""
from __future__ import annotations
from .i18n import trf as _tf
from dataclasses import dataclass, field, asdict
import copy
import math
from typing import Any
import numpy as np
from scipy import signal, fft
IDENTITY = np.array([1.0, 0.0, 0.0, 1.0, 0.0, 0.0])
KINDS = ('Peak', 'LowShelf', 'HighShelf', 'HighPass', 'LowPass', 'Notch', 'AllPass', 'SOS')

def array1(x) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if a.ndim != 1 or a.size == 0 or (not np.all(np.isfinite(a))):
        raise ValueError('Нужен непустой конечный одномерный сигнал.')
    return a

def db(h, floor=1e-14):
    return 20.0 * np.log10(np.maximum(np.abs(h), floor))

@dataclass
class Biquad:
    kind: str = 'Peak'
    name: str = 'Correction'
    f: float = 1000.0
    q: float = 1.0
    gain: float = 0.0
    enabled: bool = True
    locked: bool = False
    fmin: float = 20.0
    fmax: float = 20000.0
    qmin: float = 0.2
    qmax: float = 24.0
    gmin: float = -24.0
    gmax: float = 24.0
    raw: list[float] | None = None
    control_role: str = ''  # Explicit Zoom role; ordinary correction stays untagged.

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        values={k:v for k,v in d.items() if k in cls.__dataclass_fields__}
        # Upgrade the unreleased two-role prototype without changing coefficients.
        if values.get('control_role')=='pres':
            values['control_role']='';values['locked']=False
        return cls(**values)

    def coefficients(self, fs: float) -> np.ndarray:
        if not self.enabled:
            return IDENTITY.copy()
        if self.kind == 'SOS' or self.raw is not None:
            if self.raw is None or len(self.raw) != 6:
                raise ValueError('SOS: задайте b0,b1,b2,a0,a1,a2.')
            c = np.asarray(self.raw, dtype=float)
            if not np.all(np.isfinite(c)) or abs(c[3]) < 1e-15:
                raise ValueError('Некорректные коэффициенты SOS.')
            c = c / c[3]
            if max(abs(np.roots(c[3:]))) >= 1.0:
                raise ValueError('Неустойчивый SOS: полюс на/за единичной окружностью.')
            return c
        if self.kind not in KINDS:
            raise ValueError(_tf('Неизвестный тип BQ: {0}', self.kind))
        if not 0 < self.f < fs * 0.4999 or not 0.02 <= self.q <= 100:
            raise ValueError(_tf('{0}: неверная частота или Q/S.', self.name))
        if not np.isfinite(self.gain) or abs(self.gain) > 60:
            raise ValueError('Gain должен быть конечным и в пределах ±60 dB.')
        if self.kind in ('Peak', 'LowShelf', 'HighShelf') and abs(self.gain) < 1e-14:
            return IDENTITY.copy()
        w = 2 * np.pi * self.f / fs
        cw, sw = (np.cos(w), np.sin(w))
        alpha = sw / (2 * self.q)
        A = 10 ** (self.gain / 40)
        if self.kind == 'Peak':
            b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
            a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
        elif self.kind == 'HighPass':
            b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
            a = [1 + alpha, -2 * cw, 1 - alpha]
        elif self.kind == 'LowPass':
            b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
            a = [1 + alpha, -2 * cw, 1 - alpha]
        elif self.kind == 'Notch':
            b = [1, -2 * cw, 1]
            a = [1 + alpha, -2 * cw, 1 - alpha]
        elif self.kind == 'AllPass':
            b = [1 - alpha, -2 * cw, 1 + alpha]
            a = [1 + alpha, -2 * cw, 1 - alpha]
        else:
            if not 0.05 <= self.q <= 1.0:
                raise ValueError('Для полок используется S, допустимо 0.05…1.0 (не Q).')
            alpha = sw / 2 * np.sqrt((A + 1 / A) * (1 / self.q - 1) + 2)
            beta = 2 * np.sqrt(A) * alpha
            if self.kind == 'LowShelf':
                b = A * np.array([A + 1 - (A - 1) * cw + beta, 2 * (A - 1 - (A + 1) * cw), A + 1 - (A - 1) * cw - beta])
                a = [A + 1 + (A - 1) * cw + beta, -2 * (A - 1 + (A + 1) * cw), A + 1 + (A - 1) * cw - beta]
            else:
                b = A * np.array([A + 1 + (A - 1) * cw + beta, -2 * (A - 1 + (A + 1) * cw), A + 1 + (A - 1) * cw - beta])
                a = [A + 1 - (A - 1) * cw + beta, 2 * (A - 1 - (A + 1) * cw), A + 1 - (A - 1) * cw - beta]
        return np.r_[np.asarray(b) / a[0], 1.0, np.asarray(a)[1:] / a[0]]

def sos_array(sections: list[Biquad], fs: int, quantize=False):
    s = np.asarray([b.coefficients(fs) for b in sections], dtype=np.float64).reshape(-1, 6)
    if quantize:
        s = s.astype(np.float32).astype(np.float64)
    return s

def sos_response(sos, f, fs):
    f = np.asarray(f)
    z = np.exp(-2j * np.pi * f / fs)
    H = np.ones(len(f), dtype=complex)
    for b0, b1, b2, a0, a1, a2 in sos:
        H *= (b0 + b1 * z + b2 * z * z) / (a0 + a1 * z + a2 * z * z)
    return H

def sos_stability(sos) -> float:
    if len(sos) == 0:
        return 0.0
    return float(max((max(abs(np.roots(s[3:]))) for s in sos)))

def quantize_fir(h):
    h = array1(h)
    scale = max(1.0, float(np.max(abs(h))) / 0.95)
    q = np.clip(np.rint(h / scale * 32768), -32768, 32767).astype(np.int16)
    return (q, scale)

@dataclass
class Model:
    fs: int
    fir: np.ndarray
    sections: list[Biquad] = field(default_factory=list)
    name: str = 'Model'
    notes: str = ''
    training: dict[str, Any] = field(default_factory=dict)
    fir_enabled: bool = True
    output_gain_db: float = 0.0

    def clone(self):
        return copy.deepcopy(self)

    def to_dict(self):
        return {'fs': self.fs, 'fir': self.fir.tolist(), 'sections': [s.to_dict() for s in self.sections], 'name': self.name, 'notes': self.notes, 'training': self.training, 'fir_enabled': self.fir_enabled, 'output_gain_db': self.output_gain_db}

    @classmethod
    def from_dict(cls, d):
        fs = int(d['fs'])
        if not 8000 <= fs <= 192000:
            raise ValueError('Недопустимая частота модели.')
        h = array1(d['fir'])
        if h.size > 16384 or len(d.get('sections', [])) > 64:
            raise ValueError('Превышен размер модели.')
        sections = [Biquad.from_dict(s) for s in d.get('sections', [])]
        gain_db = float(d.get('output_gain_db', 0.0))
        if not np.isfinite(gain_db) or abs(gain_db) > 60:
            raise ValueError('Overall Gain должен быть конечным и в пределах ±60 dB.')
        m = cls(fs, h, sections, d.get('name', 'Model'), d.get('notes', ''), d.get('training', {}), bool(d.get('fir_enabled', True)), gain_db)
        sos_array(m.sections, fs)
        return m

    def response(self, f, quantized=False):
        if self.fir_enabled:
            h = self.fir
            if quantized:
                q, scale = quantize_fir(h)
                h = q.astype(float) / 32768 * scale
            F = fir_response(h, f, self.fs)
        else:
            F = np.ones(len(np.asarray(f)), dtype=complex)
        return (10 ** (self.output_gain_db / 20.0)) * F * sos_response(sos_array(self.sections, self.fs, quantized), f, self.fs)

    def render(self, length=None, quantized=False):
        s = sos_array(self.sections, self.fs, quantized)
        r = sos_stability(s)
        if r >= 1:
            raise ValueError('Квантованная модель неустойчива; экспорт/прослушивание запрещены.')
        if length is None:
            tail = int(np.ceil(np.log(1e-09) / np.log(r))) if r > 0 else 0
            base = len(self.fir) if self.fir_enabled else 1
            length = max(base, min(base + tail + 64, self.fs * 8))
        if self.fir_enabled:
            h = self.fir
            if quantized:
                q, scale = quantize_fir(h)
                h = q.astype(float) / 32768 * scale
        else:
            h = np.array([1.0])
        y = np.pad(h[:length], (0, max(0, length - len(h))))
        y = signal.sosfilt(s.copy(), y) if len(s) else y.copy()
        return y * (10 ** (self.output_gain_db / 20.0))

def fir_response(h, f, fs):
    """Direct evaluation (no sparse-FFT interpolation of narrow notches)."""
    return signal.freqz(array1(h), worN=2 * np.pi * np.asarray(f) / fs)[1]

@dataclass
class PrepConfig:
    fs: int = 44100
    channel: int = 0
    dc_tail: bool = False
    trim_start: bool = True
    trim_end: bool = False
    threshold_db: float = -90.0
    preroll_ms: float = 0.2
    postroll_ms: float = 10.0
    max_ms: float = 0.0
    fade_ms: float = 0.0
    minimum_phase: bool = True
    normalization: str = 'none'
    level_db: float = -1.0
    ir_resample_gain: bool = True
    invert_polarity: bool = False

def minimum_phase_ir(x, fft_size=None):
    """Full log-magnitude real-cepstrum reconstruction, not sqrt-spectrum conversion.
    The output retains the entire FFT-length causal approximation; no hidden crop.
    """
    x = array1(x)
    n = int(fft_size or 2 ** int(np.ceil(np.log2(max(65536, 8 * len(x))))))
    if n > 4194304:
        raise ValueError('IR слишком длинный для MPT в этой версии. Ограничьте исходную длину (max ms) или выключите MPT.')
    if n % 2 or n < len(x):
        raise ValueError('MPT FFT must be even and at least the source length.')
    X = np.fft.rfft(x, n)
    floor = max(np.max(abs(X)) * 1e-12, 1e-30)
    c = np.fft.irfft(np.log(np.maximum(abs(X), floor)), n)
    cm = np.zeros(n)
    cm[0] = c[0]
    cm[1:n // 2] = 2 * c[1:n // 2]
    cm[n // 2] = c[n // 2]
    H = np.exp(np.fft.rfft(cm))
    return np.fft.irfft(H, n)

def resample_ir(x, src_fs, dst_fs, preserve_gain=True):
    x = array1(x)
    if src_fs == dst_fs:
        return (x.copy(), 0)
    g = math.gcd(src_fs, dst_fs)
    up, down = (dst_fs // g, src_fs // g)
    pad = down * max(1, math.ceil(32 / down))
    y = signal.resample_poly(np.pad(x, (pad, pad)), up, down, window=('kaiser', 8.6))
    if preserve_gain:
        y *= src_fs / dst_fs
    return (y, pad * up // down)

def prepare(audio, src_fs: int, cfg: PrepConfig):
    a = np.asarray(audio, dtype=float)
    if a.ndim == 2:
        if cfg.channel == -1:
            x = a.mean(axis=1)
        elif 0 <= cfg.channel < a.shape[1]:
            x = a[:, cfg.channel]
        else:
            raise ValueError('Нет выбранного канала в исходном файле.')
    else:
        x = a
    x = array1(x).copy()
    if len(x) > src_fs * 30:
        raise ValueError('Файл длиннее 30 секунд. Загрузите IR, а не музыкальную запись.')
    if max(abs(x)) < 1e-15:
        raise ValueError('Сигнал пустой / выбранные каналы погасились при суммировании.')
    if not 8000 <= cfg.fs <= 192000:
        raise ValueError('Частота дискретизации вне диапазона 8…192 kHz.')
    if cfg.preroll_ms < 0 or cfg.postroll_ms < 0 or cfg.max_ms < 0 or (cfg.fade_ms < 0) or (not -180 <= cfg.threshold_db <= 0):
        raise ValueError('Времена должны быть ≥0, порог тишины −180…0 dB.')
    log = [_tf('Исходник: {0} отсч., {1} Hz.', len(x), src_fs)]
    if cfg.dc_tail:
        dc = float(np.median(x[-max(8, len(x) // 10):]))
        x -= dc
        log.append(_tf('DC по медиане последней 1/10: {0:.8g} (не среднее всего IR).', dc))
    y, pad = resample_ir(x, src_fs, cfg.fs, cfg.ir_resample_gain)
    if src_fs != cfg.fs:
        log.append(_tf('Polyphase {0} → {1} Hz; сохранён preroll {2} отсч.; компенсация коэффициентов Fs_in/Fs_out: {3}.', src_fs, cfg.fs, pad, cfg.ir_resample_gain))
    peak = float(np.max(abs(y)))
    ids = np.flatnonzero(abs(y) >= peak * 10 ** (cfg.threshold_db / 20))
    if not len(ids):
        raise ValueError('Порог тишины удаляет весь IR.')
    first = max(0, int(ids[0]) - round(cfg.preroll_ms * cfg.fs / 1000)) if cfg.trim_start else 0
    last = min(len(y), int(ids[-1]) + 1 + round(cfg.postroll_ms * cfg.fs / 1000)) if cfg.trim_end else len(y)
    y = y[first:last]
    log.append(_tf('Trim: удалено в начале {0}; сохранён интервал [{1}:{2}] resampled.', first, first, last))
    if cfg.max_ms > 0:
        y = y[:max(2, round(cfg.max_ms * cfg.fs / 1000))]
        log.append(_tf('Явное ограничение исходной длины: {0:g} ms (меняет спектр).', cfg.max_ms))
    if cfg.fade_ms > 0:
        m = min(len(y), max(2, round(cfg.fade_ms * cfg.fs / 1000)))
        y[-m:] *= 0.5 * (1 + np.cos(np.linspace(0, np.pi, m)))
        log.append(_tf('Хвостовой cosine fade: {0} отсч. до MPT.', m))
    before = y.copy()
    if cfg.minimum_phase:
        y = minimum_phase_ir(y)
        log.append(_tf('MPT: полный спектр модуля, FFT {0}; без повторной обрезки.', len(y)))
    gain = 1.0
    if cfg.normalization == 'peak':
        gain = 10 ** (cfg.level_db / 20) / np.max(abs(y))
    elif cfg.normalization in ('band', 'frequency_peak'):
        n = fft.next_fast_len(max(65536, 2 * len(y)))
        H = np.fft.rfft(y, n)
        f = np.fft.rfftfreq(n, 1 / cfg.fs)
        if cfg.normalization == 'band':
            fg = np.geomspace(80, min(8000, cfg.fs * 0.45), 4096)
            power = np.interp(fg, f, abs(H) ** 2).mean()
            gain = 10 ** (cfg.level_db / 20) / max(math.sqrt(power), 1e-20)
        else:
            gain = 10 ** (cfg.level_db / 20) / max(np.max(abs(H)), 1e-20)
    elif cfg.normalization != 'none':
        raise ValueError('Неизвестная нормализация.')
    if cfg.invert_polarity:
        gain *= -1.0
        log.append('Явная инверсия полярности (после MPT).')
    y *= gain
    before *= gain
    log.append(_tf('Нормализация: {0}; общий gain {1:.9g} / {2:+.3f} dB.', cfg.normalization, gain, 20 * np.log10(abs(gain))))
    return (y, before, log)

def frequency_grid(fs, n=5000, lo=20.0, hi=None):
    hi = min(20000.0, fs * 0.499) if hi is None else min(hi, fs * 0.499)
    return np.geomspace(lo, hi, n)

def response_metrics(T, H, f, fs, floor_db=-70.0):
    """Same absolute reference for every metric. Wrapped absolute phase + diagnostic trend."""
    T, H, f = (np.asarray(T), np.asarray(H), np.asarray(f))
    floor = max(np.max(abs(T)) * 10 ** (floor_db / 20), 1e-25)
    usable = abs(T) >= floor
    e = db(H) - db(T)
    phase = np.angle(H * np.conj(T)) * 180 / np.pi
    rows = []
    for name, lo, hi in [('all', 20, 20000.1), ('guitar', 80, 8000), ('LF', 20, 200), ('transition', 200, 500), ('mid', 500, 2000), ('high', 2000, 8000), ('top', 8000, 20000.1)]:
        m = (f >= lo) & (f < hi) & usable
        if not np.any(m):
            continue
        rows.append({'band': name, 'count': int(m.sum()), 'mag_rms_db': float(np.sqrt(np.mean(e[m] ** 2))), 'mag_max_db': float(np.max(abs(e[m]))), 'mag_p95_db': float(np.percentile(abs(e[m]), 95)), 'phase_rms_deg': float(np.sqrt(np.mean(phase[m] ** 2))), 'undefined_phase_bins': int(np.sum(m & (abs(H) < floor * 0.001)))})
    return rows

def phase_diagnostics(T, H, f, fs, lo=80, hi=8000):
    m = (f >= lo) & (f <= hi) & (abs(T) > np.max(abs(T)) * 0.0001) & (abs(H) > np.max(abs(H)) * 1e-06)
    fp = f[m]
    p = np.unwrap(np.angle(H[m] * np.conj(T[m])))
    if len(fp) < 3:
        return {'offset_deg': 0.0, 'delay_samples': 0.0, 'ripple_deg': float('nan')}
    A = np.c_[np.ones(len(fp)), fp / fp.max()]
    beta = np.linalg.lstsq(A, p, rcond=None)[0]
    r = p - A @ beta
    return {'offset_deg': float(np.degrees(beta[0])), 'delay_samples': float(-beta[1] / fp.max() * fs / (2 * np.pi)), 'ripple_deg': float(np.sqrt(np.mean(np.degrees(r) ** 2)))}

def preset_sections(count=8, lowcut=True, fs=44100):
    if not 0 <= count <= 32:
        raise ValueError('BQ: 0…32.')
    if count == 0:
        return []
    res = Biquad('Peak', 'Resonance', 120, 0.8, 3, fmin=50, fmax=220, gmin=-12, gmax=24, control_role='reso')
    pres = Biquad('HighShelf', 'Presence', min(3500, fs * 0.35), 0.8, 0, locked=False, qmin=0.1, qmax=1.0)
    if count == 1:
        return [res]
    if count == 2:
        return [res, pres]
    low = Biquad('HighPass' if lowcut else 'LowShelf', 'Low Cut' if lowcut else 'LF shelf', 40 if lowcut else 65, 0.707, 0 if lowcut else -15, fmin=10, fmax=220, qmin=0.25, qmax=1.5 if lowcut else 1.0, gmin=-42, gmax=12)
    nmid = count - 3
    centers = np.geomspace(450, 2500, max(1, nmid))
    mids = [Biquad('Peak', f'Mid {i + 1}', float(f), 1.5, 0, fmin=300, fmax=min(3000, fs * 0.4), qmax=24.0, gmin=-18, gmax=18) for i, f in enumerate(centers[:nmid])]
    return [low, res] + mids + [pres]
