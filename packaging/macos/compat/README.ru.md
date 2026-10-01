# Кандидат для macOS 13 / 12

[English](README.md)

**Дополнительный пакет только для development.** Основная цель — macOS 13 Ventura,
дополнительная — macOS 12 Monterey. Заявленный минимум бинарников — 12.3 для
Apple Silicon и Intel. Сборка и анализ заголовков на macOS 15 **не доказывают
запуск на macOS 12 или 13**. До публикации и расширения списка поддерживаемых
систем нужно проверить именно эти ZIP на целевых ОС.
Существующие Mac 15+ и Windows-архивы не заменяются.

## Правила упаковки

Первый аудит полного ARM64-приложения отклонил цель 12.0: выбранный wheel SciPy
называется `macosx_12_0`, но его модули Mach-O и библиотеки Fortran требуют **12.3**.
Поэтому общий профиль явно требует **12.3+** для обеих архитектур. Поддержка
12.0–12.2 не заявляется; строгая проверка бинарников не ослаблена.

Версии Python, приложения и DSP не меняются. Для NumPy 2.5.3 и SciPy 1.18.1
есть разные macOS wheels; обычный pip на новой ОС предпочитает варианты для 14.0.
Два requirements-файла закрепляют совместимые wheels всех зависимостей приложения
и упаковщика по точным URL и SHA-256. Заголовки бинарников не меняются ради
сокрытия требований. Для трейнера и патчинга HIR3A компилятор TI не нужен.

`../build_macos.py --profile compat12` создаёт дополнительный пакет. Профиль
`standard` по умолчанию сохраняет минимум 15.0 и прежние имена ZIP.
`../audit_macho.py` проверяет нужный срез каждого Mach-O, минимальную ОС,
Info.plist, ссылки внутри пакета и внешние абсолютные пути библиотек.
Ошибка останавливает упаковку, а не молча повышает минимум. Полной проверки
доступности символов и API этот анализ не выполняет.

Имена ZIP: `HYBRID-IR-<version>-macOS-arm64-compat12-preview.zip` и
`HYBRID-IR-<version>-macOS-x86_64-compat12-preview.zip`. Внутри — `HYBRID IR.app`,
инструкции EN/RU и метаданные. У кандидата отдельный bundle identifier, но общий
путь настроек HYBRID IR: сделайте копии данных и не запускайте обе версии одновременно.

## Сборка из генерируемого зеркала

Нужны нативный Mac, **CPython 3.14.6 с Tk** и чистое venv. Не устанавливайте затем
общие requirements: они могут заменить wheels вариантами для новой ОС.
Из корня development, после коммита исходников и пересборки зеркала по инструкции
`HYBRID-IR/publication/README.md`:

```sh
SOURCE="$PWD/HYBRID-IR/publication/repo"
REVISION=$(git rev-parse HEAD)
WORK=$(mktemp -d /tmp/hybridir-compat.XXXXXX)
ARCH=$(uname -m)
python3.14 -m venv "$WORK/venv"
"$WORK/venv/bin/python" -m pip install --force-reinstall --require-hashes --only-binary=:all: -r "$SOURCE/packaging/macos/compat/requirements-$ARCH.txt"
"$WORK/venv/bin/python" -m pip check
"$WORK/venv/bin/python" -B "$SOURCE/scripts/run_development_tests.py"
"$WORK/venv/bin/python" -B "$SOURCE/packaging/macos/build_macos.py" --source "$SOURCE" --out "$WORK/packages" --revision "$REVISION" --profile compat12
```

Сборщик проверяет точные wheels по `direct_url.json` и хеши исходников,
сканирует реальные бинарники, включая Python, Tcl/Tk, OpenBLAS/Fortran и загрузчик
PyInstaller, проверяет ad-hoc подпись и запускает перенесённое read-only приложение
напрямую и через LaunchServices. `MACOS_BUILD.json` содержит фактическую ОС сборки.
`MACOS_DEPLOYMENT.json` — статический анализ; `VALIDATION.json` — запуск на ОС
проверки. ZIP загружается в CI-артефакты лишь после успешных проверок.
`../tests/test_compat.py` содержит переносимые проверки механизма упаковки.

## Установка и проверка на целевой ОС

Выберите свою архитектуру, проверьте соседний `.zip.sha256` командой
`shasum -a 256 -c <file>.zip.sha256`, распакуйте штатной Утилитой архивирования.
Храните `.app` целиком в отдельной тестовой папке. На целевом Mac Python/Homebrew
не нужны. Сначала сделайте копии настроек, проектов, банков и исходного аудио.

Подпись остаётся **ad-hoc, без Developer ID и нотарификации Apple**. Для проверенного
пакета из доверенного источника используйте Open Anyway для конкретного приложения,
когда система это предлагает. Не отключайте Gatekeeper целиком и не обходите
предупреждения о вредоносном ПО, повреждении или несовпадении суммы.
Подпись и совпадение ZIP не гарантируют отсутствие вредоносного кода.

Сначала на настоящей macOS 13, затем на Monterey 12.3 или новее запишите версию ОС, архитектуру,
SHA-256 архива и результаты: Finder-запуск; импорт WAV; FIR + BQ обучение
(не только FIR); все K-weighted режимы; defaults после перезапуска; сохранение и
открытие проектов/банков; A/B прослушивание; экспорт HIR3A в обычную доступную папку.
Встроенный тест работает с синтетическими данными:

```sh
WORK=$(mktemp -d /tmp/hybridir-target-test.XXXXXX)
"/path/to/HYBRID IR.app/Contents/MacOS/HYBRID IR" --self-test "$WORK"
```

Сохраните `report.json` и журнал запуска. Отдельно проверьте Finder-запуск
скачанного приложения с карантином: Терминал — не тот же тест. Загрузка в педаль
и прослушивание — отдельные проверки. По одним заголовкам или запуску на macOS 15
список поддерживаемых ОС не расширяем.

Настройки: `~/Library/Application Support/HYBRID IR/settings.json`; кеш/журналы:
`~/Library/Caches/HYBRID IR/`; библиотека: `~/Documents/HYBRID IR/Library/`.
Замена или удаление целого `.app` эти файлы не удаляет. При смене версий
сохраняйте оригиналы и резервные копии.

## Происхождение и ограничения

Wheels подобраны для `macosx_12_0` / `cp314`, хеши сверены с PyPI 2026-09-30.
Прежний рецепт упаковки сохраняет уведомления о лицензиях зависимостей.
Предпочтительно собирать на самой старой поддерживаемой ОС. Этот CI использует
macOS 15 и не подтверждает запуск на 12/13 или одобрение Apple.

[Файлы NumPy](https://pypi.org/project/numpy/2.5.3/) ·
[Файлы SciPy](https://pypi.org/project/scipy/1.18.1/) ·
[Совместимость PyInstaller](https://pyinstaller.org/en/stable/usage.html#macos) ·
[Инструкция Apple по безопасности](https://support.apple.com/ru-ru/102445)
