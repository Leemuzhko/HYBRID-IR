<p align="center">
  <img src="assets/IR_CAB-1200x800.png" width="240" alt="HYBRID IR — картка двоканального кабінетного ефекту">
</p>
<h1 align="center">HYBRID IR</h1>
<p align="center"><strong>Ваш кабінет. Усередині вашого Zoom.</strong><br>
Підготовка імпульсів, гібридна FIR/IIR-апроксимація та збирання власних ZDL.</p>
<p align="center">
  <img src="https://img.shields.io/badge/Desktop-Windows-2563eb?style=flat-square" alt="Програма для Windows">
  <img src="https://img.shields.io/badge/DSP-FIR_%2B_IIR-475569?style=flat-square" alt="DSP: FIR + IIR">
  <img src="https://img.shields.io/badge/Patcher-No_TI_compiler-475569?style=flat-square" alt="Патчер без компілятора TI">
  <img src="https://img.shields.io/badge/Status-Experimental-92400e?style=flat-square" alt="Експериментальна версія">
</p>
<p align="center"><a href="README.md">English</a> · <a href="README.ru.md">Русский</a> · <strong>Українська</strong></p>
<h3 align="center"><a href="https://github.com/Leemuzhko/HYBRID-IR/archive/refs/heads/main.zip">Завантажити для Windows</a></h3>
<p align="center"><a href="#installation">Встановлення</a> · <a href="#workflow">Створити перший ефект</a> · <a href="https://ko-fi.com/leemuzhko">Підтримати на Ko-fi</a></p>
<p align="center">MS-50G · MS-60B · MS-70CDR · G1on · G1Xon · B1on<br>
<sub>Лінійка пристроїв проєкту. Перевірка на обладнанні залежить від моделі й банку; див. технічний посібник.</sub></p>

---

Я розробляю HYBRID IR, щоб використовувати власні кабінетні імпульси в педалях Zoom. Можна завантажити звичайний IR або підібрати коротший FIR із додатковими IIR-фільтрами, а потім зібрати свої кабінети в один ZDL із перемиканням слотів. Інструменти безкоштовні; для звичайного патчингу компілятор TI не потрібен.

## Документація

Якщо хочеться спочатку спробувати готові ефекти, вони є в моєму репозиторії [Zoom-ZDL-FX](https://github.com/Leemuzhko/Zoom-ZDL-FX/tree/main/zdl/). Перед встановленням прочитайте опис вибраного ефекту й перевірте сумісність. HYBRID IR потрібен для підготовки власних банків.

- [Встановлення, оновлення та видалення](docs/uk/installation.md)
- [Підготовка IR та збирання банку](docs/uk/workflow.md)
- [Обмеження й технічні подробиці](docs/uk/technical.md)

<a id="installation"></a>
<a id="workflow"></a>

## Швидкий старт

Встановіть програму, відкрийте **Zoom ZDL**, додайте імпульс через **Import WAV** і зберіть ефект кнопкою **Patch ZDL (no TI)**. Готовий ZDL завантажте через [Zoom Effect Manager](https://zoomeffectmanager.com/en/download/). Налаштування та перевірки описано в посібниках нижче.

## Перед початком

Комплектний HYBRID4 вміщує **до 4 IR + OFF**, не більш ніж **2048 відліків на імпульс**, зі **спільним пулом 4096 FIR-відліків**. Чотири різні імпульси по 2048 до нього не помістяться. Для екрана педалі використовуйте в назві слота **не більш ніж 5 символів**.

DSP-вартість навмисно занижена й зафіксована на **20** — це не відсоток навантаження. Перевіряйте весь ланцюжок на слух: якщо з'являється тріск, виберіть коротший IR або режим **L/R** з однією гілкою обробки. Сам лише IR **OFF** не вимикає гілку повністю. Перед тестом прочитайте технічний посібник.

Описані тести прототипів я проводив на **MS-70CDR із прошивкою 2.10**. Це не підтверджує роботу кожної моделі, нового банку чи комплектного експериментального шаблону. HYBRID IR — кабінетний фільтр, а не модель підсилювача чи перевантаження.

## Підтримати проєкт

Якщо HYBRID IR вам корисний, можна [підтримати мою роботу на Ko-fi](https://ko-fi.com/leemuzhko). Це допомагає мені займатися розробкою, тестами й документацією. Інструменти залишаються безкоштовними; донат не купує функцій, пріоритетної підтримки чи строку випуску.

[Вихідний код і сторонні компоненти](docs/uk/technical.md) · [MIT](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)
