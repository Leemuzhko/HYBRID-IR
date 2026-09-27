"""Application-owned Russian strings must have English catalog coverage."""
import ast
import re
import unittest
from pathlib import Path
from irbq.i18n import tr,set_language


class TestEnglishCatalog(unittest.TestCase):
    def tearDown(self):set_language('ru')

    def test_open_wav_plot_hint_uses_language_and_theme(self):
        from unittest.mock import MagicMock, patch
        from matplotlib.figure import Figure
        from matplotlib.colors import to_rgba
        from irbq.gui import BaseApp
        from irbq.ui_theme import PALETTES
        for language, expected in [('en', 'New WAV — click Prepare IR'),
                                   ('ru', 'Новый WAV — нажмите «Подготовить IR»')]:
            for theme in ('light', 'dark'):
                with self.subTest(language=language, theme=theme):
                    set_language(language)
                    app = MagicMock()
                    app.dirty = False
                    app.figure = Figure()
                    app.ax = app.figure.subplots()
                    app.colors = PALETTES[theme]
                    with patch('irbq.gui.filedialog.askopenfilename', return_value='fixture.wav'), \
                         patch('irbq.gui.Session'):
                        BaseApp.open_wav(app)
                    app.error.assert_not_called()
                    hint = app.ax.texts[0]
                    self.assertEqual(hint.get_text(), expected)
                    self.assertEqual(to_rgba(hint.get_color()), to_rgba(app.colors['fg']))

    def test_source_literals_have_english_translation(self):
        set_language('en');missing=[]
        for path in sorted((Path(__file__).resolve().parents[1]/'irbq').glob('*.py')):
            if path.name=='i18n.py':continue  # Contains the explicit Russian help variant.
            tree=ast.parse(path.read_text(encoding='utf-8'))
            parents={child:node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            for node in ast.walk(tree):
                if isinstance(node,ast.JoinedStr):
                    value=''.join(part.value if isinstance(part,ast.Constant) else '123' for part in node.values)
                    if re.search('[А-Яа-яЁё]',tr(value)):
                        missing.append(f'{path.name}:{node.lineno}: f-string {value!r}')
                    continue
                if not isinstance(node,ast.Constant) or not isinstance(node.value,str):continue
                if not re.search('[А-Яа-яЁё]',node.value):continue
                parent=parents.get(node)
                if isinstance(parent,(ast.JoinedStr,ast.Expr)):continue
                if node.value=='Русский':continue  # Native-language name in the selector.
                if path.name=='project.py' and node.value.startswith('# Экспорт IRBQ Lab\n'):
                    continue  # Deliberately Russian README_EXPORT_RU.md, not UI.
                if re.search('[А-Яа-яЁё]',tr(node.value)):
                    missing.append(f'{path.name}:{node.lineno}: {node.value!r}')
        self.assertFalse(missing,'\n'+'\n'.join(missing))

    def test_multiline_messages_and_model_data_are_preserved(self):
        set_language('en')
        text='Исходник: 512 отсч., 44100 Hz.\nЯвная инверсия полярности (после MPT).\nНет незаблокированных параметров BQ; модель не изменена.'
        self.assertFalse(re.search('[А-Яа-яЁё]',tr(text)),tr(text))
        self.assertEqual(tr('Открыт проект C:/IR/Кабинет.irbq'),'Project opened: C:/IR/Кабинет.irbq')

    def test_line_endings_reverse_and_exact_multiline_entries(self):
        set_language('en')
        source='Исходник: 512 отсч., 44100 Hz.\r\n\r\nЯвная инверсия полярности (после MPT).\n'
        translated=tr(source)
        self.assertEqual(translated.count('\r\n'),2)
        self.assertTrue(translated.endswith('\n'))
        self.assertFalse(re.search('[А-Яа-яЁё]',translated))
        set_language('ru');self.assertEqual(tr(translated),source)
        set_language('en')
        from irbq.i18n import _catalog
        for key,value in _catalog.items():
            if '\n' in key:self.assertEqual(tr(key),value)
        from irbq.i18n import trf
        template='Рендер готов. Общий monitor gain {0:.5g}; явный RMS match B: {1:.5g}.\nA и B используют одинаковый вход. Кнопки плеера начинают рендер заново; это не ABX.'
        english=trf(template,.75,1.25)
        set_language('ru');self.assertEqual(tr(english),template.format(.75,1.25))
