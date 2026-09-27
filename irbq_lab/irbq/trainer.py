"""Separable FIR/BQ optimisation with preserved complex and BQ-only magnitude objectives.

For fixed BQ theta, solve min_h ||W (H_BQ(theta)*A*h - T)||^2 + lambda||h||^2.
The reduced gradient uses the envelope theorem; gradients of the FIR solution
cancel because its normal-equation residual is zero. No neural network needed.
"""
from __future__ import annotations
from .i18n import trf as _tf
from dataclasses import dataclass, asdict
import copy
import time
from typing import Callable
import numpy as np
from scipy import linalg, optimize, ndimage, signal
from scipy.sparse.linalg import LinearOperator, lsmr
from .dsp import Model, Biquad, db, sos_array, sos_response, fir_response, frequency_grid, response_metrics

class Cancelled(Exception):
    pass

@dataclass
class TrainConfig:
    mode: str = 'pairs'
    iterations: int = 100
    rounds: int = 2
    ridge: float = 1e-06
    floor_db: float = -55.0
    profile: str = 'guitar'
    cancellation: float = 1e-05
    initialize: bool = True
    restarts: int = 1
    seed: int = 1701
    objective: str = 'auto'  # auto: BQ-only=magnitude, FIR/FIR+BQ=complex
    fit_gain: bool = True
    magnitude_delta_db: float = 6.0

def band_weights(f, profile):
    if profile == 'flat':
        return np.ones_like(f)
    v = [0.2, 0.4, 1.0, 1.5, 3.0, 3.0, 2.0, 0.8, 0.25, 0.1]
    if profile == 'mid':
        v = [0.2, 0.4, 0.8, 1.2, 5.0, 5.0, 2.0, 0.8, 0.25, 0.1]
    x = np.log([10, 40, 80, 150, 300, 3000, 8000, 10000, 20000, 96000])
    return np.interp(np.log(np.maximum(f, 1.0)), x, v)

class Engine:

    def __init__(self, target, model: Model, config: TrainConfig, cancel=None):
        self.model = model.clone()
        self.n = len(model.fir)
        if config.objective not in ('auto', 'complex', 'magnitude'):
            raise ValueError('Неизвестная целевая функция обучения.')
        self.objective_kind = ('magnitude' if config.mode == 'bq' else 'complex') if config.objective == 'auto' else config.objective
        if self.objective_kind == 'magnitude' and config.mode != 'bq':
            raise ValueError('Magnitude-fit доступен только в режиме «Только BQ». FIR/FIR+BQ сохраняет комплексную цель.')
        if config.magnitude_delta_db <= 0 or not np.isfinite(config.magnitude_delta_db):
            raise ValueError('Robust delta для magnitude-fit должен быть > 0.')
        self.fs = model.fs
        self.cfg = config
        self.cancel = cancel or (lambda: False)
        if not 4 <= self.n <= 4096:
            raise ValueError('Подбор FIR: 4…4096 отсчётов.')
        if config.ridge <= 0:
            raise ValueError('Регуляризация должна быть > 0.')
        if self.n <= 1024:
            self.iterative = False
            self.f = np.unique(np.r_[np.geomspace(10, self.fs * 0.5, 1600), np.linspace(10, self.fs * 0.5, max(2048, 4 * self.n))])
            self.w = np.gradient(np.log(self.f)) * band_weights(self.f, config.profile)
            self.E = np.exp(-2j * np.pi * np.outer(self.f / self.fs, np.arange(self.n)))
        else:
            self.iterative = True
            self.nfft = 2 ** int(np.ceil(np.log2(max(32768, 16 * self.n))))
            self.f = np.fft.rfftfreq(self.nfft, 1 / self.fs)
            self.w = band_weights(self.f, config.profile) / np.maximum(self.f, 10.0)
            self.w[self.f < 10] = 0.0
        self.w /= self.w.sum()
        self.T = fir_response(target, self.f, self.fs)
        self.scale = max(np.max(abs(self.T)), 1e-15)
        self.T = self.T / self.scale
        self.target_db = np.maximum(db(self.T), config.floor_db)
        self.norm = np.maximum(abs(self.T), 10 ** (config.floor_db / 20))
        self.s = np.sqrt(self.w) / self.norm
        self.lam = config.ridge * float(np.sum(self.s ** 2))
        if model.fir_enabled:
            self.fixed_h = model.fir / self.scale
        else:
            self.fixed_h = np.zeros(self.n, dtype=float)
            self.fixed_h[0] = 1.0 / self.scale
        self.z = np.exp(-2j * np.pi * self.f / self.fs)
        self.variables = []
        x = []
        bounds = []
        for i, b in enumerate(self.model.sections):
            if config.mode == 'fir' or not b.enabled or b.locked or (b.kind == 'SOS'):
                continue
            if b.fmin >= min(b.fmax, self.fs * 0.49) or b.qmin >= b.qmax:
                raise ValueError(_tf('{0}: некорректные границы подбора.', b.name))
            for name, val, lo, hi, logarithmic in [('f', b.f, b.fmin, min(b.fmax, self.fs * 0.49), True), ('q', b.q, b.qmin, min(b.qmax, 1.0) if 'Shelf' in b.kind else b.qmax, True)]:
                if hi <= lo:
                    continue
                self.variables.append((i, name, logarithmic))
                x.append(np.log(np.clip(val, lo, hi)))
                bounds.append((np.log(lo), np.log(hi)))
            if b.kind in ('Peak', 'LowShelf', 'HighShelf'):
                self.variables.append((i, 'gain', False))
                x.append(np.clip(b.gain, b.gmin, b.gmax))
                bounds.append((b.gmin, b.gmax))
        self.x0 = np.array(x, dtype=float)
        self.bounds = bounds
        self.calls = 0
        self.last_solver = {}
        self.started = time.perf_counter()
        self.last_gain_db = float(model.output_gain_db)

    def check(self):
        if self.cancel():
            raise Cancelled('Остановлено пользователем.')

    def decode(self, x):
        secs = copy.deepcopy(self.model.sections)
        for value, (i, key, logarithmic) in zip(x, self.variables):
            setattr(secs[i], key, float(np.exp(value) if logarithmic else value))
            secs[i].raw = None
        return secs

    def response_sections(self, x):
        secs = self.decode(x)
        sos = sos_array(secs, self.fs)
        z = self.z
        S = np.asarray([(r[0] + r[1] * z + r[2] * z * z) / (r[3] + r[4] * z + r[5] * z * z) for r in sos])
        if not len(S):
            S = np.ones((0, len(z)), dtype=complex)
        return (secs, S, np.prod(S, axis=0))

    def _fft_adjoint(self, v):
        v = v.copy()
        v[1:-1] *= 0.5
        return (self.nfft * np.fft.irfft(v, n=self.nfft))[:self.n]

    def solve(self, H):
        if self.cfg.mode == 'bq' or (not self.model.fir_enabled and self.cfg.mode in ('pairs', 'joint')):
            return self.fixed_h.copy()
        if self.iterative:
            c = H * self.s
            m = len(c)
            sq = np.sqrt(self.lam)

            def mv(h):
                self.check()
                y = np.fft.rfft(h, n=self.nfft) * c
                return np.r_[y.real, y.imag, sq * h]

            def rm(v):
                u = (v[:m] + 1j * v[m:2 * m]) * np.conj(c)
                return self._fft_adjoint(u) + sq * v[2 * m:]
            op = LinearOperator((2 * m + self.n, self.n), matvec=mv, rmatvec=rm, dtype=float)
            t = self.T * self.s
            solution = lsmr(op, np.r_[t.real, t.imag, np.zeros(self.n)], atol=2e-09, btol=2e-09, maxiter=500)
            self.last_solver = {'method': 'FFT LSMR', 'stop': int(solution[1]), 'iterations': int(solution[2])}
            return solution[0]
        v = abs(H * self.s) ** 2
        c = self.E.real.T @ v
        c[0] += self.lam
        rhs = (self.E.conj().T @ (np.conj(H) * self.T * self.s ** 2)).real
        try:
            h = linalg.solve_toeplitz((c, c), rhs, check_finite=False)
            if not np.all(np.isfinite(h)):
                raise linalg.LinAlgError('nonfinite')
            residual = linalg.matmul_toeplitz((c, c), h, check_finite=False) - rhs
            if np.linalg.norm(residual) > 1e-06 * max(np.linalg.norm(rhs), 1e-10):
                raise linalg.LinAlgError('normal residual')
            self.last_solver = {'method': 'regularized Toeplitz', 'relative_residual': float(np.linalg.norm(residual) / max(np.linalg.norm(rhs), 1e-30))}
            return h
        except (linalg.LinAlgError, ValueError):
            B = self.E * (H * self.s)[:, None]
            y = self.T * self.s
            A = np.vstack((B.real, B.imag, np.sqrt(self.lam) * np.eye(self.n)))
            b = np.r_[y.real, y.imag, np.zeros(self.n)]
            h = linalg.lstsq(A, b, lapack_driver='gelsy')[0]
            self.last_solver = {'method': 'augmented QR fallback'}
            return h

    def apply_fir(self, h):
        return np.fft.rfft(h, n=self.nfft) if self.iterative else self.E @ h

    def regularizer(self, secs, S):
        gains = [b.gain for b in secs if b.enabled and b.kind in ('Peak', 'LowShelf', 'HighShelf')]
        value = 1e-07 * float(np.sum(np.square(gains)))
        ids = [i for i, b in enumerate(secs) if b.enabled and b.kind in ('Peak', 'LowShelf', 'HighShelf')]
        if len(ids) > 1 and self.cfg.cancellation:
            curves = db(S[ids])
            cancelled = np.maximum(np.sum(abs(curves), axis=0) - abs(np.sum(curves, axis=0)) - 2.0, 0.0)
            value += self.cfg.cancellation * float(np.sum(self.w * cancelled ** 2))
        return value

    def _fit_output_gain_db(self, base_db):
        if not self.cfg.fit_gain:
            return float(self.model.output_gain_db)
        # Robust scalar location fit. This removes arbitrary IR capture level without
        # asking the BQ sections to manufacture a broadband offset.
        residual0 = self.target_db - base_db
        gain = float(np.sum(self.w * residual0))
        delta = float(self.cfg.magnitude_delta_db)
        for _ in range(8):
            r = base_db + gain - self.target_db
            u = r / delta
            den = np.sqrt(1.0 + u * u)
            grad = float(np.sum(self.w * (r / den)))
            curv = float(np.sum(self.w / (den ** 3)))
            if curv < 1e-12:
                break
            step = grad / curv
            gain = float(np.clip(gain - step, -60.0, 60.0))
            if abs(step) < 1e-9:
                break
        return gain

    def _magnitude_value(self, x):
        secs, S, H = self.response_sections(x)
        h = self.solve(H)
        F = self.apply_fir(h)
        Y = F * H
        base_db = db(Y)
        gain_db = self._fit_output_gain_db(base_db)
        residual_db = base_db + gain_db - self.target_db
        delta = float(self.cfg.magnitude_delta_db)
        u = residual_db / delta
        # Pseudo-Huber: quadratic around the optimum, linear influence for
        # unrepresentable narrow cabinet notches.
        data_loss = float(np.sum(self.w * (delta * delta) * (np.sqrt(1.0 + u * u) - 1.0)))
        reg = self.regularizer(secs, S)
        return data_loss + reg, h, secs, S, H, residual_db, gain_db

    def evaluate(self, x, gradient=True):
        self.check()
        self.calls += 1
        if self.objective_kind == 'magnitude':
            value, h, secs, S, H, residual_db, gain_db = self._magnitude_value(x)
            self.last_gain_db = float(gain_db)
            if not gradient:
                return (value, h, secs)
            grad = np.empty(len(x))
            delta_db = float(self.cfg.magnitude_delta_db)
            psi = residual_db / np.sqrt(1.0 + (residual_db / delta_db) ** 2)
            # Gain is conditionally optimal. Envelope theorem lets us ignore
            # d(gain*)/dx in the reduced gradient.
            for k, (section, key, lg) in enumerate(self.variables):
                self.check()
                step = 2e-05 if lg else 0.0002
                xp = x.copy(); xm = x.copy()
                xp[k] += step; xm[k] -= step
                lo, hi = self.bounds[k]
                xp[k] = min(xp[k], hi); xm[k] = max(xm[k], lo)
                dx = xp[k] - xm[k]
                sp, Sp, Hp = self.response_sections(xp)
                sm, Sm, Hm = self.response_sections(xm)
                dH = (Hp - Hm) / dx
                safe = np.where(np.abs(H) > 1e-18, H, 1e-18 + 0j)
                dmag_db = (20.0 / np.log(10.0)) * np.real(dH / safe)
                grad[k] = float(np.sum(self.w * psi * dmag_db))
                grad[k] += (self.regularizer(sp, Sp) - self.regularizer(sm, Sm)) / dx
            return (value, grad)

        secs, S, H = self.response_sections(x)
        gain_linear = 10 ** (self.model.output_gain_db / 20.0)
        Hg = H * gain_linear
        h = self.solve(Hg)
        F = self.apply_fir(h)
        error = F * Hg - self.T
        reg = self.regularizer(secs, S)
        value = float(np.sum(abs(error * self.s) ** 2) + self.lam * np.dot(h, h) + reg)
        self.last_gain_db = float(self.model.output_gain_db)
        if not gradient:
            return (value, h, secs)
        grad = np.empty(len(x))
        for k, (section, key, lg) in enumerate(self.variables):
            self.check()
            step = 2e-05 if lg else 0.0002
            xp = x.copy(); xm = x.copy()
            xp[k] += step; xm[k] -= step
            lo, hi = self.bounds[k]
            xp[k] = min(xp[k], hi); xm[k] = max(xm[k], lo)
            dx = xp[k] - xm[k]
            sp, Sp, Hp = self.response_sections(xp)
            sm, Sm, Hm = self.response_sections(xm)
            dH = (Hp - Hm) / dx * gain_linear
            grad[k] = 2 * np.real(np.sum(self.s ** 2 * np.conj(error) * F * dH))
            grad[k] += (self.regularizer(sp, Sp) - self.regularizer(sm, Sm)) / dx
        return (value, grad)

    def candidate_model(self, x, name=None):
        value, h, secs = self.evaluate(x, False)
        keep_fir = self.cfg.mode == 'bq' or (not self.model.fir_enabled and self.cfg.mode in ('pairs', 'joint'))
        physical_h = self.model.fir.copy() if keep_fir else h * self.scale
        gain_db = float(self.last_gain_db if self.objective_kind == 'magnitude' else self.model.output_gain_db)
        m = Model(self.fs, physical_h, secs, name or self.model.name, fir_enabled=self.model.fir_enabled, output_gain_db=gain_db)
        note = ('Robust magnitude-dB BQ fit + regularization; phase is diagnostic only.' if self.objective_kind == 'magnitude' else 'Fixed complex output error + regularization; existing FIR/FIR+BQ behaviour preserved.')
        m.training = {'objective': value, 'objective_kind': self.objective_kind, 'fitted_output_gain_db': gain_db, 'config': asdict(self.cfg), 'calls': self.calls, 'seconds': time.perf_counter() - self.started, 'solver': self.last_solver, 'note': note}
        return m

    def initial_features(self, x):
        """Greedy proposal; accept a seed ONLY after re-solving FIR and lowering same objective."""
        current = x.copy()
        val, h, secs = self.evaluate(current, False)
        H = self.apply_fir(h) * sos_response(sos_array(secs, self.fs), self.f, self.fs)
        gain_db = self.last_gain_db if self.objective_kind == 'magnitude' else self.model.output_gain_db
        correction = self.target_db - (db(H) + gain_db) if self.objective_kind == 'magnitude' else db(self.T) - (db(H) + gain_db)
        fg = np.geomspace(20, self.fs * 0.47, 1800)
        e = ndimage.gaussian_filter1d(np.interp(fg, self.f, correction), 4)
        used = []
        for i, b in enumerate(secs):
            if b.locked or not b.enabled or b.kind != 'Peak' or (abs(b.gain) > 0.4):
                continue
            ids = [k for k, v in enumerate(self.variables) if v[0] == i]
            names = {self.variables[k][1]: k for k in ids}
            if not {'f', 'q', 'gain'} <= names.keys():
                continue
            m = (fg >= b.fmin) & (fg <= min(b.fmax, self.fs * 0.47))
            peaks, _ = signal.find_peaks(abs(e), distance=10)
            peaks = [j for j in peaks if m[j] and all((abs(np.log2(fg[j] / u)) > 0.12 for u in used))]
            peaks = sorted(peaks, key=lambda j: abs(e[j]), reverse=True)[:3]
            best = None
            for j in peaks:
                for q in (1.0, 3.0, 7.0):
                    trial = current.copy()
                    trial[names['f']] = np.log(fg[j])
                    trial[names['q']] = np.log(np.clip(q, b.qmin, b.qmax))
                    trial[names['gain']] = np.clip(e[j], max(b.gmin, -8), min(b.gmax, 8))
                    tv, _, _ = self.evaluate(trial, False)
                    if tv < val and (best is None or tv < best[0]):
                        best = (tv, trial, fg[j])
            if best:
                val, current, fr = best
                used.append(fr)
                _, hh, ss = self.evaluate(current, False)
                newH = self.apply_fir(hh) * sos_response(sos_array(ss, self.fs), self.f, self.fs)
                gain_db = self.last_gain_db if self.objective_kind == 'magnitude' else self.model.output_gain_db
                residual = self.target_db - (db(newH) + gain_db) if self.objective_kind == 'magnitude' else db(self.T) - (db(newH) + gain_db)
                e = ndimage.gaussian_filter1d(np.interp(fg, self.f, residual), 4)
        return current

def train(target, model: Model, config: TrainConfig, progress: Callable | None=None, cancel=None,
          preview: Callable | None=None, preview_interval: float=0.5):
    progress = progress or (lambda percent, text: None)
    if preview is not None and (not np.isfinite(preview_interval) or preview_interval <= 0):
        raise ValueError('preview_interval must be finite and positive')
    engine = Engine(target, model, config, cancel)
    engine.last_solver = {}
    x = engine.x0.copy()
    value, h, secs = engine.evaluate(x, False)
    best_x = x.copy()
    best_value = value
    next_preview = 0.0

    def publish_preview(candidate):
        nonlocal next_preview
        if preview is not None and time.perf_counter() >= next_preview:
            # Detached model only; the worker must never touch Tk or the session.
            preview(engine.candidate_model(candidate))
            next_preview = time.perf_counter() + preview_interval

    publish_preview(best_x)
    history = [{'stage': 'conditional FIR solve' if engine.objective_kind == 'complex' else 'BQ magnitude fit', 'objective': value, 'objective_kind': engine.objective_kind}]
    path = f'{len(model.fir)} FIR + {len(model.sections)} BQ' if model.fir_enabled else f'FIR BYPASS + {len(model.sections)} BQ'
    progress(1, _tf('Старт: {0}; loss={1:.6g}', path + ' / ' + engine.objective_kind, value))
    if config.mode == 'fir' or not len(x):
        result = engine.candidate_model(x)
        result.training['history'] = history
        if config.mode == 'fir':
            progress(100, 'FIR пересчитан; параметры BQ не изменялись.')
        elif engine.objective_kind == 'magnitude' and config.fit_gain:
            progress(100, _tf('Overall Gain подобран: {0:+.3f} dB; параметры BQ не изменялись.', result.output_gain_db))
        else:
            progress(100, 'Нет незаблокированных параметров BQ; модель не изменена.')
        return result
    if engine.iterative and config.mode != 'bq' and model.fir_enabled:
        raise ValueError('Совместный подбор FIR ограничен 1024 taps; при выключенном FIR можно обучать BQ и на длинной сохранённой FIR-модели.')
    rng = np.random.default_rng(config.seed)
    restarts = max(1, min(config.restarts, 8))
    completed = 0
    for restart in range(restarts):
        engine.check()
        x = best_x.copy()
        if restart:
            for k, (_, key, lg) in enumerate(engine.variables):
                x[k] += rng.normal(0, 0.08 if lg else 0.6)
                x[k] = np.clip(x[k], *engine.bounds[k])
        if config.initialize:
            x = engine.initial_features(x)
        groups = []
        if config.mode == 'pairs':
            section_ids = sorted(set((v[0] for v in engine.variables)))
            for _ in range(max(1, config.rounds)):
                for start in range(0, len(section_ids), 2):
                    group = section_ids[max(0, start - 1):start + 2]
                    groups.append([k for k, v in enumerate(engine.variables) if v[0] in group])
            groups.append(list(range(len(x))))
        else:
            groups = [list(range(len(x)))]
        for group_index, ids in enumerate(groups):
            base = x.copy()
            local_best = [engine.evaluate(x, False)[0], x.copy()]
            counter = [0]

            def objective(v):
                full = base.copy()
                full[ids] = v
                score, grad = engine.evaluate(full, True)
                if score < local_best[0]:
                    local_best[:] = [score, full.copy()]
                publish_preview(local_best[1] if local_best[0] < best_value else best_x)
                counter[0] += 1
                if counter[0] % 8 == 0:
                    pct = 5 + 90 * (restart + (group_index + min(counter[0] / max(config.iterations, 1), 0.9)) / len(groups)) / restarts
                    progress(int(pct), _tf('Запуск {0}/{1}; группа {2}/{3}; loss={4:.6g}', restart + 1, restarts, group_index + 1, len(groups), local_best[0]))
                return (score, grad[ids])
            r = optimize.minimize(objective, x[ids], jac=True, method='L-BFGS-B', bounds=[engine.bounds[k] for k in ids], options={'maxiter': int(config.iterations), 'maxls': 20, 'ftol': 1e-10, 'gtol': 1e-07})
            x = local_best[1]
            v = local_best[0]
            history.append({'restart': restart, 'group': group_index, 'objective': float(v), 'iterations': int(r.nit), 'success': bool(r.success), 'message': str(r.message)})
            if v < best_value:
                best_value = v
                best_x = x.copy()
            progress(int(5 + 90 * (restart + (group_index + 1) / len(groups)) / restarts), _tf('Группа завершена: loss={0:.6g}. {1}', v, r.message))
    result = engine.candidate_model(best_x)
    result.training['history'] = history
    progress(100, _tf('Готово: loss {0:.6g} → {1:.6g}; {2} оценок.', value, best_value, engine.calls))
    return result
