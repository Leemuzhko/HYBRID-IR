<p align="center">
  <img src="assets/IR_CAB-1200x800.png" width="240" alt="HYBRID IR — карточка двухканального кабинетного эффекта">
</p>
<h1 align="center">HYBRID IR</h1>
<p align="center"><strong>Ваш кабинет. Внутри вашего Zoom.</strong><br>
Подготовка импульсов, гибридная FIR/IIR-аппроксимация и сборка собственных ZDL.</p>
<p align="center">
  <img src="https://img.shields.io/badge/Desktop-Windows-2563eb?style=flat-square" alt="Программа для Windows">
  <img src="https://img.shields.io/badge/DSP-FIR_%2B_IIR-475569?style=flat-square" alt="DSP: FIR + IIR">
  <img src="https://img.shields.io/badge/Patcher-No_TI_compiler-475569?style=flat-square" alt="Патчер без компилятора TI">
  <img src="https://img.shields.io/badge/Status-Experimental-92400e?style=flat-square" alt="Экспериментальная версия">
</p>
<p align="center"><a href="README.md">English</a> · <strong>Русский</strong> · <a href="README.uk.md">Українська</a></p>
<h3 align="center"><a href="https://github.com/Leemuzhko/HYBRID-IR/archive/refs/heads/main.zip">Скачать для Windows</a></h3>
<p align="center"><a href="#installation">Установка</a> · <a href="#workflow">Создать первый эффект</a> · <a href="https://ko-fi.com/leemuzhko">Поддержать на Ko-fi</a></p>
<p align="center">MS-50G · MS-60B · MS-70CDR · G1on · G1Xon · B1on<br>
<sub>Линейка устройств проекта. Аппаратная проверка зависит от модели и банка; см. техническое руководство.</sub></p>

---

Я делаю HYBRID IR, чтобы использовать свои кабинетные импульсы в педалях Zoom. Можно загрузить обычный IR или подобрать более короткий FIR с дополнительными IIR-фильтрами, а затем собрать свои кабинеты в один ZDL с переключаемыми слотами. Инструменты бесплатны; для обычного патчинга компилятор TI не нужен.

## Документация

Если хочется сначала попробовать готовые эффекты, они лежат в моём репозитории [Zoom-ZDL-FX](https://github.com/Leemuzhko/Zoom-ZDL-FX/tree/main/zdl/). Перед установкой прочитайте описание выбранного эффекта и проверьте совместимость. HYBRID IR нужен для подготовки собственных банков.

- [Установка, обновление и удаление](docs/ru/installation.md)
- [Подготовка IR и сборка банка](docs/ru/workflow.md)
- [Ограничения и технические детали](docs/ru/technical.md)

<a id="installation"></a>
<a id="workflow"></a>

## Быстрый старт

Установите программу, откройте **Zoom ZDL**, добавьте импульс через **Import WAV** и соберите эффект кнопкой **Patch ZDL (no TI)**. Готовый ZDL загрузите через [Zoom Effect Manager](https://zoomeffectmanager.com/ru/download/). Настройки и проверки разобраны в руководствах ниже.

## Перед началом

Комплектный HYBRID4 вмещает **до 4 IR + OFF**, не более **2048 отсчётов на импульс**, с **общим пулом 4096 FIR-отсчётов**. Четыре разных импульса по 2048 в него не поместятся. Для экрана педали оставляйте в имени слота **не более 5 символов**.

DSP-стоимость намеренно занижена и зафиксирована на **20** — это не процент загрузки. Проверяйте всю цепь на слух: при треске выберите более короткий IR или режим **L/R** с одной веткой обработки. Один только IR **OFF** не отключает ветку целиком. Перед тестом прочитайте техническое руководство.

Описанные тесты прототипов я проводил на **MS-70CDR с прошивкой 2.10**. Это не подтверждает работу каждой модели, нового банка или комплектного экспериментального шаблона. HYBRID IR — кабинетный фильтр, а не модель усилителя или перегруза.

## Поддержать проект

Если HYBRID IR вам полезен, можно [поддержать мою работу на Ko-fi](https://ko-fi.com/leemuzhko). Это помогает мне заниматься разработкой, тестами и документацией. Инструменты остаются бесплатными; донат не покупает функции, приоритетную поддержку или срок выпуска.

[Исходники и сторонние компоненты](docs/ru/technical.md) · [MIT](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)
