"""Tk/ttk desktop UI. All lengthy preparation/training/rendering runs off the UI thread."""
from __future__ import annotations
import copy
import csv
import sys
import json
import queue
import threading
import traceback
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import numpy as np
import soundfile as sf
from scipy import ndimage
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from .dsp import *
from .trainer import train, TrainConfig, Cancelled
from .project import Session, export_model, import_models
from .audio import Player, render_ab
from . import __version__
from .i18n import tr as _, trf as _tf, ChoiceVar, DisplayVar
from .ui_theme import theme_widgets, theme_axes
PLOTS = ['АЧХ', 'ΔАЧХ: модель − эталон', 'ФЧХ: без выравнивания', 'ΔФЧХ: относительно эталона', 'Групповая задержка', 'Импульс', 'BQ по секциям', 'Комплексная разность Hmodel − Href']
PRESET = {'LowShelf + Resonance + Mid + Presence': False, 'LowCut + Resonance + Mid + Presence': True}
MODE_NAMES = {'Попарно + совместный polish': 'pairs', 'Все BQ + FIR совместно': 'joint', 'Только BQ (с текущим состоянием FIR)': 'bq'}
NORM_NAMES = {'Без нормализации': 'none', 'Пик импульса': 'peak', 'Средняя мощность H, 80–8000 Hz': 'band', 'Максимум |H|': 'frequency_peak'}
PROFILE_NAMES = {'Гитара 80–8000 Hz': 'guitar', 'Акцент 300–3000 Hz': 'mid', 'Равный вес на октаву': 'flat'}
OBJECTIVE_NAMES = {'Авто (рекомендуется)': 'auto', 'Магнитуда dB (только BQ)': 'magnitude', 'Комплексная: амплитуда + фаза': 'complex'}

def set_combo(parent, values, var, width=20):
    return ttk.Combobox(parent, textvariable=var, values=[_(str(v)) for v in values], width=width, state='readonly')

class ScrollPanel(ttk.Frame):

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, width=300)
        self.scroll = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.scroll.pack(side='right', fill='y')
        self.body = ttk.Frame(self.canvas, padding=10)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind_wheel_tree()

    def bind_wheel_tree(self, root=None):
        root = root or self
        def visit(widget):
            widget.bind('<MouseWheel>', self._route_wheel, add='+')
            widget.bind('<Button-4>', self._route_wheel, add='+')
            widget.bind('<Button-5>', self._route_wheel, add='+')
            for child in widget.winfo_children():
                visit(child)
        visit(root)

    def _route_wheel(self, event):
        if getattr(event, 'num', None) == 4:
            units = -1
        elif getattr(event, 'num', None) == 5:
            units = 1
        else:
            delta = getattr(event, 'delta', 0)
            if not delta:
                return None
            units = -1 if delta > 0 else 1
        self.canvas.yview_scroll(units * 3, 'units')
        return 'break'

class BQEditor(tk.Toplevel):

    def __init__(self, parent, b: Biquad, fs, callback):
        super().__init__(parent)
        self.title(_('Редактор BQ — параметры и ограничения'))
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.b = copy.deepcopy(b)
        self.callback = callback
        self.fs = fs
        pane = ttk.Frame(self, padding=16)
        pane.pack(fill='both', expand=True)
        self.vars = {}
        labels = [('name', 'Название'), ('kind', 'Тип'), ('f', 'Частота, Hz'), ('q', 'Q / S для shelf'), ('gain', 'Gain, dB'), ('fmin', 'Авто: F min'), ('fmax', 'Авто: F max'), ('qmin', 'Авто: Q/S min'), ('qmax', 'Авто: Q/S max'), ('gmin', 'Авто: Gain min'), ('gmax', 'Авто: Gain max')]
        for row, (key, label) in enumerate(labels):
            ttk.Label(pane, text=_(label)).grid(row=row, column=0, sticky='w', padx=4, pady=4)
            v = ChoiceVar(value=b.kind, choices=KINDS) if key == 'kind' else tk.StringVar(value=str(getattr(b, key)))
            self.vars[key] = v
            widget = set_combo(pane, KINDS, v, 28) if key == 'kind' else ttk.Entry(pane, textvariable=v, width=31)
            widget.grid(row=row, column=1, sticky='ew', padx=4, pady=4)
        self.on = tk.BooleanVar(value=b.enabled)
        self.lock = tk.BooleanVar(value=b.locked)
        ttk.Checkbutton(pane, text=_('Включён'), variable=self.on).grid(row=11, column=0, sticky='w')
        ttk.Checkbutton(pane, text=_('Lock: не обучать'), variable=self.lock).grid(row=11, column=1, sticky='w')
        ttk.Label(pane, text=_('Прямые SOS (тип SOS): b0, b1, b2, a0, a1, a2')).grid(row=12, column=0, columnspan=2, sticky='w', pady=(10, 2))
        self.raw = tk.StringVar(value=', '.join((f'{x:.12g}' for x in b.raw or IDENTITY.tolist())))
        ttk.Entry(pane, textvariable=self.raw, width=70).grid(row=13, column=0, columnspan=2, sticky='ew')
        ttk.Label(pane, text=_('Shelf использует S ≤ 1. SOS проверяется на устойчивость.\nРучное изменение параметров отменяет точный SOS импортированной секции.')).grid(row=14, column=0, columnspan=2, sticky='w', pady=9)
        self.err = ttk.Label(pane, text=_(''), wraplength=510)
        self.err.grid(row=15, column=0, columnspan=2, sticky='w')
        buttons = ttk.Frame(pane)
        buttons.grid(row=16, column=0, columnspan=2, sticky='e', pady=6)
        ttk.Button(buttons, text=_('Отмена'), command=self.destroy).pack(side='left', padx=5)
        ttk.Button(buttons, text=_('Применить'), command=self.apply).pack(side='left')
        self.bind('<Return>', lambda e: self.apply())
        self.bind('<Escape>', lambda e: self.destroy())
        if hasattr(parent, 'colors'):
            theme_widgets(self, parent.colors)

    def apply(self):
        try:
            new = copy.deepcopy(self.b)
            for k, v in self.vars.items():
                val = v.get().strip()
                setattr(new, k, val if k in ('name', 'kind') else float(val.replace(',', '.')))
            new.enabled = self.on.get()
            new.locked = self.lock.get()
            changed = any((getattr(new, k) != getattr(self.b, k) for k in ('kind', 'f', 'q', 'gain')))
            if new.kind == 'SOS':
                new.raw = [float(v) for v in self.raw.get().replace(';', ',').split(',')]
                new.locked = True
            elif changed:
                new.raw = None
            if new.fmin <= 0 or new.qmin <= 0 or new.fmin >= new.fmax or (new.qmin >= new.qmax) or (new.gmin >= new.gmax):
                raise ValueError(_('Min должен быть меньше Max.'))
            enabled = new.enabled
            new.enabled = True
            new.coefficients(self.fs)
            new.enabled = enabled
            self.callback(new)
            self.destroy()
        except Exception as e:
            self.err.configure(text=_(str(e)))

class BaseApp(tk.Tk):

    def __init__(self):
        super().__init__()
        icon=Path(__file__).resolve().parents[2]/'assets/zoom-ms70cdr.ico'
        if sys.platform=='win32' and icon.is_file():self.iconbitmap(str(icon))
        self.title(_(f'IRBQ Lab {__version__} — Cabinet IR / FIR + Biquad'))
        self.geometry('1440x970')
        self.minsize(1060, 760)
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        self.option_add('*Font', '{Segoe UI} 10')
        style.configure('TButton', padding=(8, 5))
        style.configure('Title.TLabel', font=('Segoe UI', 16, 'bold'))
        style.configure('Small.TLabel', font=('Segoe UI', 9))
        self.session = Session()
        self.project_path = None
        self.undo_stack = []
        self.redo_stack = []
        self.events = queue.Queue()
        self.preview_events = queue.Queue(maxsize=1)
        self.training_preview = None
        self.cancel_event = threading.Event()
        self.busy = False
        self.redraw_id = None
        self.target_cache = {}
        self.player = Player()
        self.audio_render = None
        self.audio_file = None
        self.dirty = False
        self._make_ui()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)
        self.bind('<Control-o>', lambda e: self.open_wav())
        self.bind('<Control-s>', lambda e: self.save_project())
        self.bind('<Control-z>', lambda e: self.undo())
        self.bind('<Control-y>', lambda e: self.redo())

    def _prep_ui(self, p):
        self.pvars = {}

        def field(label, key, value, values=None):
            ttk.Label(p, text=_(label)).pack(anchor='w', pady=(7, 2))
            v = ChoiceVar(value=str(value), choices=list(values)) if values is not None else tk.StringVar(value=str(value))
            self.pvars[key] = v
            w = set_combo(p, values, v, 27) if values else ttk.Entry(p, textvariable=v)
            w.pack(fill='x')
            return v
        field('Выбор канала', 'channel', 'Канал 1', ['Канал 1', 'Канал 2', 'Среднее L+R'])
        field('Целевая Fs, Hz', 'fs', 44100, [22050, 32000, 44100, 48000, 88200, 96000, 192000])
        for text, key, default in [('Компенсировать gain IR при SRC', 'ir_resample_gain', True), ('Убрать DC по хвосту', 'dc_tail', False), ('Удалить тишину в начале', 'trim_start', True), ('Удалить тишину в хвосте', 'trim_end', False)]:
            v = tk.BooleanVar(value=default)
            self.pvars[key] = v
            ttk.Checkbutton(p, text=_(text), variable=v).pack(anchor='w', pady=3)
        field('Порог тишины, dB относительно пика', 'threshold_db', -90)
        row = ttk.Frame(p)
        row.pack(fill='x', pady=5)
        for text, key, val in [('До, ms', 'preroll_ms', 0.2), ('После, ms', 'postroll_ms', 10)]:
            cell = ttk.Frame(row)
            cell.pack(side='left', expand=True, fill='x', padx=2)
            ttk.Label(cell, text=_(text)).pack(anchor='w')
            v = tk.StringVar(value=str(val))
            self.pvars[key] = v
            ttk.Entry(cell, textvariable=v, width=10).pack(fill='x')
        field('Ограничить исходник, ms (0 = весь)', 'max_ms', 0)
        field('Fade-out исходника, ms (0 = нет)', 'fade_ms', 0)
        v = tk.BooleanVar(value=True)
        self.pvars['minimum_phase'] = v
        ttk.Checkbutton(p, text=_('Minimum-phase transform (MPT)'), variable=v).pack(anchor='w', pady=9)
        v = tk.BooleanVar(value=False)
        self.pvars['invert_polarity'] = v
        ttk.Checkbutton(p, text=_('Инвертировать полярность'), variable=v).pack(anchor='w', pady=3)
        field('Нормализация', 'normalization', 'Без нормализации', NORM_NAMES)
        field('Целевой уровень нормализации, dB', 'level_db', -1)
        ttk.Button(p, text=_('Применить подготовку'), command=self.preprocess).pack(fill='x', pady=12)
        ttk.Label(p, text=_('Подготовка создаёт новый эталон и сбрасывает\nмодель/снимки. Перед этим сохраните проект.\nDC и обрезка хвоста выключены по умолчанию.'), style='Small.TLabel').pack(anchor='w')

    def _fit_ui(self, p):
        self.taps = tk.StringVar(value='128')
        self.count = tk.StringVar(value='8')
        ttk.Label(p, text=_('Длина FIR / количество BQ')).pack(anchor='w')
        row = ttk.Frame(p)
        row.pack(fill='x', pady=5)
        ttk.Combobox(row, textvariable=self.taps, values=[32, 64, 96, 128, 192, 256, 512, 1024, 2048, 4096], width=10).pack(side='left', padx=3)
        ttk.Combobox(row, textvariable=self.count, values=[0, 2, 3, 4, 6, 8, 12, 16, 24, 32], width=10).pack(side='left', padx=3)
        self.preset = ChoiceVar(value=next(iter(PRESET)), choices=list(PRESET))
        ttk.Label(p, text=_('Роли секций')).pack(anchor='w', pady=(10, 2))
        set_combo(p, PRESET, self.preset, 28).pack(fill='x')
        ttk.Button(p, text=_('Создать / заменить структуру'), command=self.new_structure).pack(fill='x', pady=6)
        firbox = ttk.LabelFrame(p, text=_('FIR в тракте'), padding=7)
        firbox.pack(fill='x', pady=(8, 4))
        self.fir_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(firbox, text=_('FIR включён в модель / прослушивание'), variable=self.fir_enabled, command=self.toggle_fir_path).pack(anchor='w')
        ttk.Button(firbox, text=_('BQ-only: выключить FIR и обучить BQ'), command=self.train_bq_bypass).pack(fill='x', pady=(6, 2))
        ttk.Button(firbox, text=_('Включить FIR + пересчитать под текущие BQ'), command=self.enable_and_refit_fir).pack(fill='x', pady=2)
        ttk.Label(firbox, text=_('Выключение FIR = identity/bypass. Сохранённые taps не удаляются и можно включить их позже.'), style='Small.TLabel', wraplength=270).pack(anchor='w', pady=(4, 0))
        self.mode = ChoiceVar(value=next(iter(MODE_NAMES)), choices=list(MODE_NAMES))
        ttk.Label(p, text=_('Режим обучения')).pack(anchor='w', pady=(12, 3))
        set_combo(p, MODE_NAMES, self.mode, 28).pack(fill='x')
        self.objective = ChoiceVar(value=next(iter(OBJECTIVE_NAMES)), choices=list(OBJECTIVE_NAMES))
        ttk.Label(p, text=_('Целевая функция')).pack(anchor='w', pady=(10, 3))
        set_combo(p, OBJECTIVE_NAMES, self.objective, 28).pack(fill='x')
        self.fit_gain = tk.BooleanVar(value=True)
        ttk.Checkbutton(p, text=_('Авто-подбор Overall Gain'), variable=self.fit_gain).pack(anchor='w', pady=(6, 2))
        self.profile = ChoiceVar(value=next(iter(PROFILE_NAMES)), choices=list(PROFILE_NAMES))
        ttk.Label(p, text=_('Частотные веса')).pack(anchor='w', pady=(12, 3))
        set_combo(p, PROFILE_NAMES, self.profile, 28).pack(fill='x')
        self.fitvars = {}
        for text, k, v in [('Итераций на группу', 'iterations', 100), ('Проходов пар', 'rounds', 2), ('Перезапусков', 'restarts', 1), ('FIR ridge λ (масштаб)', 'ridge', '1e-6'), ('Floor эталона, dB', 'floor_db', -55), ('Штраф компенсации BQ', 'cancellation', '1e-5'), ('Magnitude robust delta, dB', 'magnitude_delta_db', 6)]:
            ttk.Label(p, text=_(text)).pack(anchor='w', pady=(9, 2))
            var = tk.StringVar(value=str(v))
            self.fitvars[k] = var
            ttk.Entry(p, textvariable=var).pack(fill='x')
        self.greedy = tk.BooleanVar(value=True)
        ttk.Checkbutton(p, text=_('Предложить пики по residual'), variable=self.greedy).pack(anchor='w', pady=10)
        ttk.Button(p, text=_('Обучить незаблокированные'), command=self.start_train).pack(fill='x', pady=4)
        ttk.Button(p, text=_('Независимый sweep вариантов…'), command=self.sweep).pack(fill='x', pady=4)
        ttk.Button(p, text=_('Чистый FIR / обрезка…'), command=self.pure_snapshot).pack(fill='x', pady=4)
        ttk.Label(p, text=_('Presence по умолчанию: 0 dB и Lock.\nBQ count включает Presence.\nFIR можно полностью обойти и сначала обучить только BQ.\nСовместное обучение FIR: ≤ 1024 taps.\nЛокальный минимум ≠ предел архитектуры.'), style='Small.TLabel').pack(anchor='w', pady=12)

    def _bq_values(self, b):
        return ('✓' if b.enabled else '—', '●' if b.locked else '', b.name, b.kind + ('*' if b.raw is not None else ''), f'{b.f:.2f}', f'{b.q:.3f}', f'{b.gain:+.2f}' if b.kind not in ('HighPass', 'LowPass', 'Notch', 'AllPass', 'SOS') else '—', f'{b.fmin:g}…{b.fmax:g}')

    def _update_bq_row(self, i):
        if self.session.model is None or not 0 <= i < len(self.session.model.sections):
            return
        iid = str(i)
        if self.bqtree.exists(iid):
            self.bqtree.item(iid, values=self._bq_values(self.session.model.sections[i]))

    def eq_neutral(self):
        if not self.guard() or self.session.model is None:
            return
        i = self.selected_bq()
        if i is None:
            return
        b = self.session.model.sections[i]
        if b.kind not in ('Peak', 'LowShelf', 'HighShelf'):
            return
        self.push_undo()
        b.gain = 0.0
        b.raw = None
        self.manual_bq_changed(i)

    def _variants_ui(self, p):
        row = ttk.Frame(p)
        row.pack(fill='x', pady=3)
        for text, cmd in [('Снимок текущей', self.snapshot), ('Взять выбранный', self.use_snapshot), ('Удалить', self.delete_snapshot), ('Добавить pure FIR', self.pure_snapshot), ('Экспорт всех', self.export_snapshots)]:
            ttk.Button(row, text=_(text), command=cmd).pack(side='left', padx=3)
        ttk.Label(p, text=_('Выделенные строки накладываются на график (Ctrl — несколько, максимум 4). Каждый снимок хранит реальные коэффициенты.'), style='Small.TLabel').pack(anchor='w', pady=3)
        cols = ('name', 'taps', 'bq', 'mag', 'phase')
        treeframe = ttk.Frame(p); treeframe.pack(fill='both', expand=True)
        self.stree = ttk.Treeview(treeframe, columns=cols, show='headings', height=6, selectmode='extended')
        for c, t in zip(cols, ['Вариант', 'FIR', 'BQ', '80–8k: RMS dB', '80–8k: фаза RMS °']):
            self.stree.heading(c, text=_(t))
            self.stree.column(c, width=100 if c != 'name' else 230, stretch=True)
        self.stree.pack(side='left', fill='both', expand=True)
        ssb=ttk.Scrollbar(treeframe,orient='vertical',command=self.stree.yview);ssb.pack(side='right',fill='y');self.stree.configure(yscrollcommand=ssb.set)
        if hasattr(self,'_bind_wheel_scroll'):self._bind_wheel_scroll(self.stree,self.stree)
        self.stree.bind('<<TreeviewSelect>>', lambda e: self.schedule_plot())
        self.stree.bind('<Double-1>', lambda e: self.use_snapshot())

    def _listen_ui(self, p):
        ttk.Label(p, text=_('Офлайн A/B через одинаковый вход. По умолчанию — тестовый шум + два тона; можно загрузить DI / запись до 30 s.')).pack(anchor='w')
        row = ttk.Frame(p)
        row.pack(fill='x', pady=8)
        ttk.Button(row, text=_('Загрузить DI / аудио…'), command=self.load_di).pack(side='left', padx=3)
        ttk.Button(row, text=_('Тестовый сигнал'), command=self.use_test_signal).pack(side='left', padx=3)
        self.match_rms = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text=_('Явно выровнять RMS модели к эталону'), variable=self.match_rms, command=self.invalidate_audio).pack(side='left', padx=8)
        self.di_label = ttk.Label(p, text=_('Вход: тестовый сигнал'))
        self.di_label.pack(anchor='w')
        vrow = ttk.Frame(p)
        vrow.pack(fill='x', pady=4)
        ttk.Label(vrow, text=_('Громкость прослушивания, dB:')).pack(side='left')
        self.preview_db = tk.StringVar(value='-12')
        ttk.Spinbox(vrow, textvariable=self.preview_db, from_=-60, to=0, increment=3, width=7).pack(side='left', padx=6)
        ttk.Label(vrow, text=_('(только плеер, не коэффициенты / экспорт)'), style='Small.TLabel').pack(side='left')
        row = ttk.Frame(p)
        row.pack(fill='x', pady=10)
        for label, key in [('Рендер A/B', None), ('▶ Эталон A', 'A'), ('▶ Модель B', 'B'), ('▶ Разность B−A', 'D')]:
            ttk.Button(row, text=_(label), command=self.prepare_audio if key is None else lambda k=key: self.play(k)).pack(side='left', padx=3)
        ttk.Button(row, text=_('■ Стоп'), command=self.player.stop).pack(side='left', padx=3)
        ttk.Button(row, text=_('Сохранить A/B WAV…'), command=self.save_audio).pack(side='left', padx=3)
        self.audio_note = ttk.Label(p, text=_('Рендер нужен после каждого изменения модели. Общий защитный gain сохраняет разницу уровней A/B.\nПереключение плеера начинает запись заново; это не real-time VST и не слепой ABX.'), wraplength=950)
        self.audio_note.pack(anchor='w', pady=8)

    def log(self, text):
        self.logtext.insert('end', _(str(text)) + '\n')
        self.logtext.see('end')

    def guard(self, target=True):
        if self.busy:
            messagebox.showinfo(_('Задача выполняется'), _('Сначала остановите или дождитесь текущей операции.'), parent=self)
            return False
        if target and self.session.target is None:
            messagebox.showinfo(_('Нет эталона'), _('Откройте WAV и нажмите «Подготовить IR».'), parent=self)
            return False
        return True

    def push_undo(self):
        if self.session.model:
            self.undo_stack.append(self.session.model.clone())
            self.undo_stack = self.undo_stack[-30:]
            self.redo_stack = []
        self.dirty = True

    def undo(self):
        if not self.guard() or not self.undo_stack:
            return
        self.redo_stack.append(self.session.model.clone())
        self.session.model = self.undo_stack.pop()
        self.changed()

    def redo(self):
        if not self.guard() or not self.redo_stack:
            return
        self.undo_stack.append(self.session.model.clone())
        self.session.model = self.redo_stack.pop()
        self.changed()

    def changed(self):
        self.audio_render = None
        self.player.stop()
        self.dirty = True
        self.refresh_bq()
        self.schedule_plot()
        if self.session.model:
            self.taps.set(str(len(self.session.model.fir)))
            self.count.set(str(len(self.session.model.sections)))
            if hasattr(self, 'fir_enabled'):
                self.fir_enabled.set(bool(self.session.model.fir_enabled))
        if hasattr(self, 'eqax'):
            self.draw_eq_editor()

    def read_prep(self):
        d = {k: v.get() for k, v in self.pvars.items()}
        for k in ['threshold_db', 'preroll_ms', 'postroll_ms', 'max_ms', 'fade_ms', 'level_db']:
            d[k] = float(str(d[k]).replace(',', '.'))
        d['fs'] = int(d['fs'])
        d['channel'] = {'Канал 1': 0, 'Канал 2': 1, 'Среднее L+R': -1}[d['channel']]
        d['normalization'] = NORM_NAMES[d['normalization']]
        return PrepConfig(**d)

    def sync_prep(self):
        d = asdict(self.session.config)
        d['channel'] = {0: 'Канал 1', 1: 'Канал 2', -1: 'Среднее L+R'}.get(d['channel'], 'Канал 1')
        d['normalization'] = next((k for k, v in NORM_NAMES.items() if v == d['normalization']))
        for k, v in d.items():
            self.pvars[k].set(v)

    def open_wav(self):
        if not self.guard(False):
            return
        p = filedialog.askopenfilename(title=_('Импульс кабинета'), filetypes=[('Audio', '*.wav *.flac *.aif *.aiff'), ('All', '*')])
        if not p:
            return
        if self.dirty and (not messagebox.askyesno(_('Новый WAV'), _('Текущие несохранённые изменения будут потеряны. Продолжить?'), parent=self)):
            return
        try:
            cfg = self.read_prep()
            s = Session(config=cfg)
            s.load_audio(p)
            self.session = s
            self.project_path = None
            self.undo_stack = []
            self.redo_stack = []
            self.target_cache = {}
            self.file_label.configure(text=_(f'{s.source_name}  |  {s.source_fs} Hz'))
            self.refresh_bq()
            self.refresh_snapshots()
            self.player.stop()
            self.audio_render = None
            self.ax.clear()
            self.ax.text(0.5, 0.5, _('Новый WAV — нажмите «Подготовить IR»'), ha='center', transform=self.ax.transAxes)
            if hasattr(self, 'colors'):
                theme_axes(self.figure, self.ax, self.colors)
            self.canvas.draw_idle()
            self.log('Открыт ' + str(p))
            self.status.set('Настройте подготовку и нажмите «Подготовить IR».')
            self.dirty = False
        except Exception as e:
            self.error(e)

    def preprocess(self):
        if not self.guard(False):
            return
        if self.session.source is None:
            self.open_wav()
            return
        if self.session.model and self.dirty and (not messagebox.askyesno(_('Новый эталон'), _('Повторная подготовка сбросит модель и снимки. Продолжить?'), parent=self)):
            return
        try:
            cfg = self.read_prep()
        except Exception as e:
            self.error(e)
            return
        s = copy.deepcopy(self.session)
        s.config = cfg

        def task():
            s.preprocess()
            return s

        def done(value):
            self.session = value
            self.target_cache = {}
            self.undo_stack = []
            self.redo_stack = []
            for text in value.log:
                self.log(text)
            self.refresh_snapshots()
            self.changed()
            self.status.set(_tf('Эталон готов: {0} Hz, {1} отсч. Выберите структуру / обучение.', value.config.fs, len(value.target)))
        self.run_job(task, done, 'Подготовка IR…')

    def new_structure(self):
        if not self.guard():
            return
        try:
            n = int(self.taps.get())
            count = int(self.count.get())
            if not 4 <= n <= 4096:
                raise ValueError(_('FIR: 4…4096.'))
            self.push_undo()
            h = np.pad(self.session.target[:n], (0, max(0, n - len(self.session.target))))
            self.session.model = Model(self.session.config.fs, h, preset_sections(count, PRESET[self.preset.get()], self.session.config.fs), f'{n}+{count} BQ')
            self.changed()
            self.status.set('Структура создана. Начальное FIR — префикс; нажмите «Обучить» / «Пересчитать FIR».')
        except Exception as e:
            self.error(e)

    def toggle_fir_path(self):
        if self.session.model is None:
            return
        desired = bool(self.fir_enabled.get())
        if desired == bool(self.session.model.fir_enabled):
            return
        if not self.guard():
            self.fir_enabled.set(bool(self.session.model.fir_enabled))
            return
        self.push_undo()
        self.session.model.fir_enabled = desired
        self.changed()
        self.status.set('FIR включён.' if desired else 'FIR BYPASS: модель и прослушивание используют только BQ.')

    def train_bq_bypass(self):
        if not self.guard():
            return
        self.push_undo()
        self.session.model.fir_enabled = False
        self.fir_enabled.set(False)
        self.changed()
        self.start_train('bq', push_history=False)

    def enable_and_refit_fir(self):
        if not self.guard():
            return
        self.push_undo()
        self.session.model.fir_enabled = True
        self.fir_enabled.set(True)
        self.changed()
        self.start_train('fir', push_history=False)

    def train_config(self, mode=None):
        vals = {k: v.get() for k, v in self.fitvars.items()}
        for k in ['iterations', 'rounds', 'restarts']:
            vals[k] = int(vals[k])
        for k in ['ridge', 'floor_db', 'cancellation', 'magnitude_delta_db']:
            vals[k] = float(vals[k])
        if not 1 <= vals['iterations'] <= 2000 or not 1 <= vals['rounds'] <= 10 or (not 1 <= vals['restarts'] <= 8):
            raise ValueError(_('Итерации 1…2000, проходы 1…10, перезапуски 1…8.'))
        if not -120 <= vals['floor_db'] <= -10 or vals['ridge'] <= 0 or vals['cancellation'] < 0 or vals['magnitude_delta_db'] <= 0:
            raise ValueError(_('Проверьте floor / ridge / штраф компенсации / robust delta.'))
        return TrainConfig(mode=mode or MODE_NAMES[self.mode.get()], profile=PROFILE_NAMES[self.profile.get()], initialize=self.greedy.get(), objective=OBJECTIVE_NAMES[self.objective.get()], fit_gain=bool(self.fit_gain.get()), **vals)

    def start_train(self, mode=None, push_history=True):
        if not self.guard():
            return
        try:
            cfg = self.train_config(mode)
        except Exception as e:
            self.error(e)
            return
        m = self.session.model.clone()
        target = self.session.target.copy()
        try:
            mismatch = int(self.taps.get()) != len(m.fir) or int(self.count.get()) != len(m.sections)
        except ValueError:
            self.error(ValueError(_('FIR и BQ должны быть целыми числами.')))
            return
        if mismatch:
            messagebox.showinfo(_('Структура'), _('Поля FIR/BQ отличаются от текущей модели. Сначала нажмите «Создать / заменить структуру».'), parent=self)
            return
        if push_history:
            self.push_undo()

        def task():
            return train(target, m, cfg, progress=lambda v, t: self.events.put(('progress', (v, t))),
                         cancel=self.cancel_event.is_set, preview=self.publish_training_preview)

        def done(model):
            self.session.model = model
            self.changed()
            self.log('Обучение: ' + json.dumps(model.training, ensure_ascii=False))
        self.run_job(task, done, 'Подбор FIR/BQ…')

    def refit_fir(self):
        self.start_train('fir')

    def sweep(self):
        if not self.guard():
            return
        text = simpledialog.askstring(_('Независимый sweep'), _('FIR+BQ через запятую. BQ включает Presence.'), initialvalue='64+4,64+8,64+16,128+8,256+4,512+2', parent=self)
        if not text:
            return
        try:
            specs = [tuple(map(int, t.strip().split('+'))) for t in text.split(',')]
            if any((len(t) != 2 or not 4 <= t[0] <= 1024 or (not 0 <= t[1] <= 32) for t in specs)) or len(specs) > 12:
                raise ValueError(_('До 12 вариантов; FIR 4…1024; BQ 0…32.'))
            cfg = self.train_config()
            fs = self.session.config.fs
            target = self.session.target.copy()
            lowcut = PRESET[self.preset.get()]
        except Exception as e:
            self.error(e)
            return

        def task():
            result = []
            for i, (n, bq) in enumerate(specs):
                m = Model(fs, np.pad(target[:n], (0, max(0, n - len(target)))), preset_sections(bq, lowcut, fs), f'{n}+{bq} independent')

                def prog(p, t):
                    self.events.put(('progress', ((i + p / 100) / len(specs) * 100, f'{i + 1}/{len(specs)} {n}+{bq}: {t}')))
                r = train(target, m, cfg, progress=prog, cancel=self.cancel_event.is_set,
                          preview=self.publish_training_preview)
                self.events.put(('snapshot', r))
                result.append(r)
            return len(result)

        def done(count):
            self.status.set(_tf('Sweep: {0} независимых моделей в списке вариантов.', count))
        self.run_job(task, done, 'Независимый sweep…')

    def selected_bq(self):
        sel = self.bqtree.selection()
        return int(sel[0]) if sel else None

    def add_bq(self):
        if not self.guard():
            return
        if len(self.session.model.sections) >= 32:
            self.error(ValueError(_('Максимум 32 секции.')))
            return

        def accept(b):
            self.push_undo()
            self.session.model.sections.append(b)
            self.changed()
        BQEditor(self, Biquad(), self.session.config.fs, accept)

    def edit_bq(self):
        if not self.guard():
            return
        i = self.selected_bq()
        if i is None:
            return

        def accept(b):
            self.push_undo()
            self.session.model.sections[i] = b
            self.changed()
        BQEditor(self, self.session.model.sections[i], self.session.config.fs, accept)

    def toggle_bq(self):
        if not self.guard():
            return
        i = self.selected_bq()
        if i is not None:
            self.push_undo()
            self.session.model.sections[i].enabled = not self.session.model.sections[i].enabled
            self.changed()

    def lock_bq(self):
        if not self.guard():
            return
        i = self.selected_bq()
        if i is not None:
            self.push_undo()
            self.session.model.sections[i].locked = not self.session.model.sections[i].locked
            self.changed()

    def remove_bq(self):
        if not self.guard():
            return
        i = self.selected_bq()
        if i is not None:
            self.push_undo()
            self.session.model.sections.pop(i)
            self.changed()

    def move_bq(self, d):
        if not self.guard():
            return
        i = self.selected_bq()
        if i is None or not 0 <= i + d < len(self.session.model.sections):
            return
        self.push_undo()
        s = self.session.model.sections
        s[i], s[i + d] = (s[i + d], s[i])
        self.changed()
        self.bqtree.selection_set(str(i + d))

    def refresh_bq(self):
        selected = self.selected_bq()
        self.bqtree.delete(*self.bqtree.get_children())
        if self.session.model is None:
            return
        for i, b in enumerate(self.session.model.sections):
            self.bqtree.insert('', 'end', iid=str(i), values=self._bq_values(b))
        if selected is not None and selected < len(self.session.model.sections):
            self.bqtree.selection_set(str(selected))
        elif self.session.model.sections:
            self.bqtree.selection_set('0')
        if hasattr(self, 'eq_kind'):
            self.sync_eq_quick()

    def snapshot(self):
        if not self.guard():
            return
        name = simpledialog.askstring(_('Снимок модели'), _('Название'), initialvalue=self.session.model.name, parent=self)
        if not name:
            return
        m = self.session.model.clone()
        m.name = name
        self.session.snapshots.append(m)
        self.dirty = True
        self.refresh_snapshots()
        self.stree.selection_set(str(len(self.session.snapshots) - 1))

    def pure_snapshot(self):
        if not self.guard():
            return
        n = simpledialog.askinteger(_('Pure FIR'), _('Длина префикса исходного подготовленного IR'), initialvalue=1024, minvalue=4, maxvalue=16384, parent=self)
        if n:
            h = np.pad(self.session.target[:n], (0, max(0, n - len(self.session.target))))
            self.session.snapshots.append(Model(self.session.config.fs, h, [], f'Pure FIR {n}'))
            self.dirty = True
            self.refresh_snapshots()

    def refresh_snapshots(self):
        self.stree.delete(*self.stree.get_children())
        if self.session.target is None:
            return
        f, T = self.target_response()
        for i, m in enumerate(self.session.snapshots):
            rows = response_metrics(T, m.response(f), f, m.fs)
            r = next((r for r in rows if r['band'] == 'guitar'), rows[0])
            taps = f'{len(m.fir)}' if m.fir_enabled else f'{len(m.fir)} (OFF)'
            self.stree.insert('', 'end', iid=str(i), values=(m.name, taps, len(m.sections), f"{r['mag_rms_db']:.3f}", f"{r['phase_rms_deg']:.2f}"))

    def use_snapshot(self):
        if not self.guard():
            return
        selected = self.stree.selection()
        if not selected:
            return
        self.push_undo()
        self.session.model = self.session.snapshots[int(selected[0])].clone()
        self.changed()

    def delete_snapshot(self):
        if not self.guard():
            return
        for i in sorted([int(i) for i in self.stree.selection()], reverse=True):
            self.session.snapshots.pop(i)
        self.dirty = True
        self.refresh_snapshots()
        self.schedule_plot()

    def target_response(self):
        if 'response' not in self.target_cache:
            f = frequency_grid(self.session.config.fs, 5000)
            self.target_cache['response'] = (f, fir_response(self.session.target, f, self.session.config.fs))
        return self.target_cache['response']

    def save_project(self, save_as=False):
        if not self.guard():
            return
        path = self.project_path
        if save_as or not path:
            path = filedialog.asksaveasfilename(defaultextension='.irbq', filetypes=[('IRBQ project', '*.irbq')], initialfile='Cabinet.irbq')
        if not path:
            return
        try:
            self.session.save(path)
            self.project_path = path
            self.dirty = False
            self.status.set('Сохранён проект: ' + str(path))
        except Exception as e:
            self.error(e)

    def open_project(self, path=None):
        if not self.guard(False):
            return
        if path is None:
            path = filedialog.askopenfilename(filetypes=[('IRBQ project', '*.irbq')])
        if not path:
            return
        if self.dirty and (not messagebox.askyesno(_('Открыть проект'), _('Несохранённые изменения будут потеряны. Продолжить?'), parent=self)):
            return
        try:
            self.session = Session.load(path)
            self.project_path = str(path)
            self.target_cache = {}
            self.undo_stack = []
            self.redo_stack = []
            self.sync_prep()
            self.file_label.configure(text=_(f'{self.session.source_name} | {self.session.config.fs} Hz'))
            self.refresh_snapshots()
            self.changed()
            self.dirty = False
            self.status.set('Открыт проект ' + str(path))
        except Exception as e:
            self.error(e)

    def import_model(self):
        if not self.guard():
            return
        p = filedialog.askopenfilename(filetypes=[('Model JSON', '*.json')])
        if not p:
            return
        try:
            models = import_models(p)
            if any((m.fs != self.session.config.fs for m in models)):
                raise ValueError(_('Fs модели отличается от эталона. Переподготовьте WAV на Fs модели. BQ нельзя просто ресемплировать.'))
            self.push_undo()
            if len(models) == 1:
                self.session.model = models[0]
            else:
                self.session.snapshots.extend(models)
                self.refresh_snapshots()
            self.changed()
            self.log('Импорт: ' + p + '; точные SOS сохранены до ручного редактирования/обучения.')
        except Exception as e:
            self.error(e)

    def import_bq(self):
        if not self.guard():
            return
        p = filedialog.askopenfilename(filetypes=[('BQ CSV', '*.csv')])
        if not p:
            return
        try:
            sections = []
            imported_gain = None
            with open(p, encoding='utf-8-sig', newline='') as handle:
                for r in csv.DictReader(handle):
                    if imported_gain is None and r.get('overall_gain_db','').strip():
                        imported_gain = float(r['overall_gain_db'])
                    if {'b0', 'b1', 'b2', 'a0', 'a1', 'a2'} <= r.keys():
                        b = Biquad('SOS', f'SOS {len(sections) + 1}', locked=True, raw=[float(r[k]) for k in ['b0', 'b1', 'b2', 'a0', 'a1', 'a2']])
                    else:
                        name = r.get('section', r.get('Section', 'Correction'))
                        kind = r.get('kind', r.get('Type', ''))
                        if kind not in KINDS:
                            kind = 'HighPass' if name.lower() in ('lowcut', 'low cut') else 'HighShelf' if name.lower() == 'presence' else 'LowShelf' if 'shelf' in name.lower() else 'Peak'
                        f0 = float(r.get('f0_Hz', r.get('f0', 1000)))
                        q = float(r.get('Q', r.get('Q_or_S', 0.8)))
                        g = r.get('Gain_dB', '0')
                        g = float(g) if g and g.lower() != 'nan' else 0.0
                        b = Biquad(kind, name, f0, q, g, locked=name.lower() == 'presence', qmax=1.0 if 'Shelf' in kind else 24.0)
                        if kind == 'SOS' and r.get('raw_json'):
                            b.raw = json.loads(r['raw_json'])
                            b.locked = True
                        if 'enabled' in r:
                            b.enabled = r['enabled'].lower() in ('1', 'true', 'yes')
                        if 'locked' in r and kind != 'SOS':
                            b.locked = r['locked'].lower() in ('1', 'true', 'yes')
                    b.coefficients(self.session.config.fs)
                    sections.append(b)
            if len(sections) > 32:
                raise ValueError(_('Не больше 32 BQ.'))
            self.push_undo()
            self.session.model.sections = sections
            if imported_gain is not None:
                self.session.model.output_gain_db = imported_gain
            self.changed()
        except Exception as e:
            self.error(e)

    def export(self):
        if not self.guard():
            return
        p = filedialog.askdirectory(title=_('Папка для экспорта модели'))
        if not p:
            return
        s = copy.deepcopy(self.session)
        dest = Path(p) / ('IRBQ_' + ''.join((c if c.isalnum() or c in '_-' else '_' for c in s.model.name)))
        if dest.exists() and (not messagebox.askyesno(_('Экспорт'), _('Файлы в ' + str(dest) + ' будут перезаписаны. Продолжить?'), parent=self)):
            return
        self.run_job(lambda: export_model(dest, s), lambda r: self.status.set('Экспорт сохранён: ' + str(dest)), 'Экспорт и проверка квантования…')

    def export_snapshots(self):
        if not self.guard() or not self.session.snapshots:
            return
        p = filedialog.askdirectory(title=_('Экспорт всех снимков в новые подпапки'))
        if not p:
            return
        s = copy.deepcopy(self.session)

        def task():
            for i, m in enumerate(s.snapshots):
                if self.cancel_event.is_set():
                    raise Cancelled()
                s.model = m
                dest = Path(p) / f'{i + 1:02d}_{len(m.fir)}FIR_{len(m.sections)}BQ'
                if dest.exists():
                    j = 2
                    while dest.with_name(dest.name + f'_{j}').exists():
                        j += 1
                    dest = dest.with_name(dest.name + f'_{j}')
                export_model(dest, s)
            return len(s.snapshots)
        self.run_job(task, lambda n: self.status.set(_tf('Экспортировано моделей: {0}', n)), 'Экспорт снимков…')

    def save_plot(self):
        p = filedialog.asksaveasfilename(defaultextension='.png', filetypes=[('PNG', '*.png')], initialfile='IRBQ_response.png')
        if p:
            try:
                self.figure.savefig(p, dpi=170)
                self.status.set('График сохранён: ' + p)
            except Exception as e:
                self.error(e)

    def load_di(self):
        if not self.guard():
            return
        p = filedialog.askopenfilename(filetypes=[('Audio', '*.wav *.flac *.aif *.aiff')])
        if p:
            self.audio_file = p
            self.di_label.configure(text=_('Вход: ' + Path(p).name))
            self.invalidate_audio()

    def use_test_signal(self):
        if not self.guard():
            return
        self.audio_file = None
        self.di_label.configure(text=_('Вход: тестовый сигнал'))
        self.invalidate_audio()

    def invalidate_audio(self):
        self.audio_render = None
        self.player.stop()

    def prepare_audio(self):
        if not self.guard():
            return
        target = self.session.target.copy()
        m = self.session.model.clone()
        p = self.audio_file
        match = self.match_rms.get()

        def done(value):
            self.audio_render = value
            self.audio_note.configure(text=_(_tf('Рендер готов. Общий monitor gain {0:.5g}; явный RMS match B: {1:.5g}.\nA и B используют одинаковый вход. Кнопки плеера начинают рендер заново; это не ABX.', value[2]['shared_monitor_gain'], value[2]['model_rms_match_gain'])))
        self.run_job(lambda: render_ab(target, m, p, match), done, 'Рендер сравнения A/B…')

    def play(self, key):
        if self.audio_render is None:
            messagebox.showinfo(_('Нужен рендер'), _('Нажмите «Рендер A/B».'), parent=self)
            return
        try:
            level = float(self.preview_db.get())
            if not -60 <= level <= 0:
                raise ValueError(_('Громкость: −60…0 dB.'))
            self.player.play(self.audio_render[0][key] * 10 ** (level / 20), self.audio_render[1])
        except Exception as e:
            self.error(e)

    def save_audio(self):
        if self.audio_render is None:
            messagebox.showinfo(_('Нужен рендер'), _('Нажмите «Рендер A/B».'), parent=self)
            return
        p = filedialog.askdirectory(title=_('Сохранить A/B/разность WAV'))
        if p:
            try:
                for key, a in self.audio_render[0].items():
                    sf.write(Path(p) / f'IRBQ_{key}.wav', a, self.audio_render[1], subtype='FLOAT')
                (Path(p) / 'IRBQ_monitor_gain.json').write_text(json.dumps(self.audio_render[2], indent=2))
                self.status.set('A/B WAV сохранены в ' + p)
            except Exception as e:
                self.error(e)

    def publish_training_preview(self, model):
        """Worker-side, bounded latest-frame mailbox; no Tk calls."""
        try:
            self.preview_events.get_nowait()
        except queue.Empty:
            pass
        self.preview_events.put_nowait(model)

    def clear_training_preview(self):
        self.training_preview = None
        try:
            self.preview_events.get_nowait()
        except queue.Empty:
            pass

    def run_job(self, fn, done, title, cancellable=True):
        self.clear_training_preview()
        self.job_cancellable = cancellable
        self.busy = True
        self.cancel_event.clear()
        self.progress['value'] = 0
        self.status.set(title)
        for b in self.action_buttons + getattr(self, 'appearance_controls', []):
            b.state(['disabled'])

        def worker():
            try:
                self.events.put(('done', (done, fn())))
            except Cancelled:
                self.events.put(('cancelled', None))
            except Exception as e:
                self.events.put(('error', (str(e), traceback.format_exc())))
        threading.Thread(target=worker, daemon=True).start()

    def cancel(self):
        self.player.stop()
        if self.busy:
            if not getattr(self, 'job_cancellable', True):
                self.status.set(_('Дождитесь завершения сборки ZDL.'))
                return
            self.cancel_event.set()
            self.status.set('Остановка на ближайшей границе вычисления…')

    def poll(self):
        try:
            for event_index in range(30):
                kind, data = self.events.get_nowait()
                if kind == 'progress':
                    self.progress['value'] = data[0]
                    self.status.set(data[1])
                elif kind == 'snapshot':
                    self.session.snapshots.append(data)
                    self.dirty = True
                    self.refresh_snapshots()
                else:
                    self.busy = False
                    self.clear_training_preview()
                    self.schedule_plot()
                    for b in self.action_buttons + getattr(self, 'appearance_controls', []):
                        b.state(['!disabled'])
                    if kind == 'done':
                        self.progress['value'] = 100
                        callback, value = data
                        callback(value)
                    elif kind == 'cancelled':
                        self.status.set('Остановлено. Исходная модель сохранена; завершённые sweep-варианты оставлены.')
                    else:
                        self.log(data[1])
                        self.error(RuntimeError(_(data[0])))
        except queue.Empty:
            pass
        except Exception as e:
            self.error(e)
        if self.busy:
            try:
                self.training_preview = self.preview_events.get_nowait()
                self.schedule_plot()
            except queue.Empty:
                pass
        self.after(100, self.poll)

    def error(self, e):
        self.status.set(str(e))
        messagebox.showerror(_('IRBQ Lab'), _(str(e)), parent=self)

    def close(self):
        if self.busy and not getattr(self, 'job_cancellable', True):
            messagebox.showinfo(_('IRBQ Lab'), _('Дождитесь завершения сборки ZDL.'), parent=self)
            return
        if hasattr(self,'zoom_panel') and self.zoom_panel.dirty:
            if not messagebox.askyesno(_('Выйти'),'Zoom bank has unsaved changes. Exit without saving?',parent=self):return
        if self.busy:
            if not messagebox.askyesno(_('Выйти'), _('Прервать текущую задачу и выйти?'), parent=self):
                return
            self.cancel_event.set()
        elif self.dirty:
            if not messagebox.askyesno(_('Выйти'), _('Есть несохранённые изменения. Выйти без сохранения?'), parent=self):
                return
        self.player.close()
        self.destroy()

def launch(project=None):
    app = App()
    if project:
        app.after(300, lambda: app.open_project(project))
    app.mainloop()
from .workspace import WorkspaceMixin

class App(WorkspaceMixin, BaseApp):
    """Unified, localised editor, preserving the existing authoring engine."""
    pass
