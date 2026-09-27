"""Application-owned UI strings. Project/model data and numeric interchange keys stay unchanged."""
from __future__ import annotations
import json
import re
import string
from pathlib import Path
import tkinter as tk

_language='ru'
_catalog=json.loads(Path(__file__).with_name('translations.json').read_text(encoding='utf-8')) if Path(__file__).with_name('translations.json').exists() else {}
_en=dict(_catalog)
_ru={v:k for k,v in _en.items()}
# Immutable canonical shape identifiers are never stored as translated strings.
KIND_TEXT={
 'Peak':('Пик / колокол','Bell / peak'), 'LowShelf':('НЧ-полка','Low shelf'),
 'HighShelf':('ВЧ-полка','High shelf'),'HighPass':('Срез НЧ','Low cut'),
 'LowPass':('Срез ВЧ','High cut'),'Notch':('Режектор','Notch'),
 'AllPass':('Фазовый','All-pass'),'SOS':('Прямые SOS','Direct SOS')}


def _compile_templates(mapping):
    result=[]
    for source,dest in mapping.items():
        if '{' not in source:continue
        parts=[];names=[]
        try:
            for literal,field,spec,conversion in string.Formatter().parse(source):
                parts.append(re.escape(literal))
                if field is not None:
                    parts.append('([^\r\n]*?)');names.append(field)
            if names:result.append((re.compile('^'+''.join(parts)+'$',re.S),names,dest))
        except ValueError:pass
    return result

_templates_en=_compile_templates(_en)
_templates_ru=_compile_templates(_ru)


def set_language(value):
    global _language
    if value not in ('ru','en'):raise ValueError('Unsupported language')
    _language=value

def get_language():return _language

def tr(text):
    if not isinstance(text,str):return text
    if text=='HELP_030' and _language=='ru':
        return '1. Открыть WAV → подготовить IR → создать структуру или импортировать модель.\n2. Для отдельного EQ: FIR BYPASS → «Только BQ» → цель «Авто». В этом режиме оптимизируется АЧХ в dB, а Overall Gain может подбираться отдельно.\n3. Для FIR/FIR+BQ «Авто» сохраняет прежнюю комплексную цель амплитуда+фаза.\n4. «Редактировать» включает точки на основном графике. Drag: частота / усиление; колесо: Q/S; Shift: точно; двойной щелчок: обход.\n5. «Отдельные BQ» включаются независимо от редактирования. Внизу: «Фильтр» — Overall Gain и ползунки; «Все BQ» — таблица. Lock защищает только от обучения.\n6. После BQ-only можно включить FIR и пересчитать его под текущие BQ. Настройки: язык и светлая/тёмная тема.\n\nАЧХ и фаза не выравниваются скрыто. Detrend — только диагностика графика. Колесо прокручивает прокручиваемые панели под курсором.\nПрослушивание — офлайн A/B, не real-time мониторинг. Программа не собирает ZDL.\nПолная инструкция: README_RU.md.'
    if text in KIND_TEXT:return KIND_TEXT[text][0 if _language=='ru' else 1]
    mapping=_ru if _language=='ru' else _en
    if text in mapping:return mapping[text]
    for pattern,names,translation in (_templates_ru if _language=='ru' else _templates_en):
        match=pattern.fullmatch(text)
        if match:
            values=dict(zip(names,match.groups()));pieces=[]
            for literal,field,_,__ in string.Formatter().parse(translation):
                pieces.append(literal)
                if field is not None:pieces.append(values.get(field,''))
            return ''.join(pieces)
    # Preserve exact entries and multi-line templates before translating log
    # blocks per line. Template fields cannot swallow neighbouring messages.
    if '\n' in text or '\r' in text:
        return ''.join(tr(line.rstrip('\r\n'))+line[len(line.rstrip('\r\n')):]
                       for line in text.splitlines(keepends=True))
    if _language=='ru':return text
    # Dynamic messages from existing DSP code: longest known prefix/suffix first.
    # This also preserves filenames/model names inserted between known fragments.
    for source,translation in sorted(_en.items(),key=lambda p:len(p[0]),reverse=True):
        if not source or not re.search('[А-Яа-яЁё]',source):continue
        if text.startswith(source):return translation+tr(text[len(source):])
        if text.endswith(source):return tr(text[:-len(source)])+translation
    return text

def trf(source,*args,**kwargs):return tr(source).format(*args,**kwargs)

class ChoiceVar(tk.StringVar):
    """Display translated labels, return stable canonical choices to application logic."""
    def __init__(self,master=None,value=None,choices=(),**kwargs):
        self.choices=list(choices)
        super().__init__(master=master,**kwargs)
        if value is not None:self.set(value)
    def get(self):
        value=super().get()
        for choice in self.choices:
            if value==str(tr(choice)) or value==str(choice):return str(choice)
        return value
    def set(self,value):return super().set(tr(str(value)))

class DisplayVar(tk.StringVar):
    """Translate application status text at assignment, without translating editable user data."""
    def set(self,value):
        self.source=value
        return super().set(tr(str(value)))
