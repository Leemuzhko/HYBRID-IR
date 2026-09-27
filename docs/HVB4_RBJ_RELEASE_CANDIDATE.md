# HVB4RBJ — Trainer 0.4.0 template, user-reported functional PASS

Owner for current HYBRID IR role/RBJ/fade validation, 2026-09-27.
Contract: [ADR0014](adr/0014-trained-reso-and-runtime-rbj-controls.md).
Included in the Trainer 0.4.0 source distribution. The three test exports received a user-reported
functional hardware PASS on2026-09-27 (scope below). Previous8-slot HVB2 reports remain
valid only for those older artifacts. GJ_IR and the user's bank are untouched.

## Layout and controls

HVB4/HBM4, header64B `<16I>`, continuous regions:
`48*E`, `8*E`, `2*F`, `20*Q`, `244`, `12`, `0`.
Exact bank bytes: `64+56*E+2*F+20*Q+256`.
Descriptor fields after scale/gain store `cos(w), sin(w)/(2Q), 10^(gain/40)`
for RESO; remaining five floats/flags are zero. The12B common region stores
PRES `cos(w),sin(w),1/S-1`. No coefficient table. Host checks CRC; immutable
runtime bank validation and cache assumptions remain those of ADR0013.
Helpers retain legacy `gj_v2_*` names internally but only accept HVB4 here.

Trained RESO owns one BQ; ordinary Presence is retained as correction, common
PRES adds one BQ. Tagged128+8 becomes9. Generic8 becomes10. OFF: no FIR or
correction, standard RESO110Hz/Q.7 and common PRES3500Hz/S.8, with branch Level.
Page2/3: `RESO | IR-L/R | PRES`; page1 and card mapping remain order2.
Range is delta−15..+15dB, step.5, persistent decimal display; unityLevel100.
Legacy nominal gain/shape is preserved. Old filter Lock without role metadata
remains the user's setting; new Presence is unlocked by default.

Control smoothing remains active. RBJ uses reciprocal and one sqrt for shelf
only on coefficient updates. Native host tests do not model C674 intrinsic
rounding or CPU time. Every actual derived denominator is guarded in C.
Serial fade:64 out /128 in samples per channel ≈1.45/2.90ms at44100Hz,
plus block alignment/history initialization. This is a short dip, not a seamless
crossfade. Rapid requests coalesce/defer; old/new FIR are never run concurrently.

## Build and gates

Synthetic template SHA256:
`b21528b5a6444dbe6200cf73b450643da22082c0e865a6c86e4cb4b298357894`.
`.text=22720`, `.audio=0`, `.const=2208`, `.fardata=144` bytes, ZDL29618.
Code+const cap28904 leaves6184B const, including1672B prefix;
bank budget4512B before alignment. These values are template-specific.
Service tables: dynsym720/dynstr503/hash368/rela.dyn1824; no growth allowed.
New IDs are required for test exports; old effects/saved presets not overwritten.

Reproduce from the worktree:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\build_hvb4_rbj_template.py --output results\hybridir\fresh-hvb4
cd irbq_lab
..\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_zoom_roles tests.test_hybrid_rbj_runtime tests.test_zoom_variable_patch tests.test_zoom_variable_bank tests.test_zoom_bank tests.test_zoom_patch tests.test_core -q
```

Current targeted gate:87 tests passed, including actual native C coefficient
accuracy, exact nominal coefficients, neutral9BQ audio comparison, malformed
banks, state canaries, routing, rapid switches, fade-before-selection commit,
compiler-free exports, relocation, trainable Presence and no-output-on-overflow.
GUI/workspace/localization gate:28 tests passed. Publication scanner:7 tests
passed;12-page documentation check passed. Snapshot scan has no pattern matches
(heuristic only). A fresh isolated source snapshot passed25 codec/native/export
tests. TI smoke passed, and all three test artifacts below were independently
rebuilt with TI and matched the compiler-free export byte-for-byte. Each inverse
repack returned the original template. A second clean template build produced
the exact pinned SHA256 above. Independent read-only review against87881ac,
including in-scope untracked files, found no defensible findings in the DSP,
role persistence, GUI, repack, hash gates or publication allowlist. No fix rounds
were needed. The reviewer's GUI run lacked Tcl; the primary's configured GUI28
PASS is the GUI evidence, not that inconclusive reviewer run.

Pedal packages: canonical project `outputs/CAB_FILTER_LAB/patched_zdl/HVB4_RBJ_20260927/`.
All17 copied files match source SHA256. No archives, old IDs or user banks replaced.

| File / ID | Test bank | Code + const bytes | SHA256 |
| --- | --- | ---: | --- |
| HBUNIT /741 |1×32,2 BQ |24928 |a60e2b45ed00159ca034a1302b4d359319c06f1b80480dcb0f8e55e3db2bec54 |
| HB9BQ /742 |1×1024,9 BQ |27096 |3b62e3cf07489f820f1f5319bf449c953c9a41bd9b097157b78c137a4596993b |
| HB8RBJ /743 |8×128,9 BQ/slot |28744 |5935cf49a5c5a74eec1be76a21a33530493d43bda816c8b47f303028d1d708b2 |

Exact sections/rebuild checks: `results/hybridir/hvb4-rbj-acceptance-20260927-a/pedal/verification.json`.
Graphify maintenance preflight was deferred: the existing manifest has no
`.graphify_root`/`.graphify_python` corpus settings. The old navigation graph is
preserved, not silently rebuilt or represented as indexing this change.

## Hardware gate

### User report,2026-09-27

User: «Все тестовые эффекты работают корректно».
In the current test context this refers to HBUNIT741, HB9BQ742 and HB8RBJ743
from `HVB4_RBJ_20260927/`. Record all three as **PASS — user-reported functional**.
Their local SHA256 values were rechecked and match the table above; this does
not independently measure which bytes were installed on the pedal.

The report supports practical operation of these exports on the user's pedal,
not a measured DSP margin or universal bank capacity. Cold-start conditions,
individual knob/MODE/OFF checks, save/reload, sustained rapid-switch behavior
and amp-chain load were not separately described in this report. Do not turn
the general PASS into separate measured results for those cases.

### Remaining detailed checks

First sole slot: add effect, card/pages, all knobs, OFF, all four MODE,
save/reload. Then compare neutral/RESO/PRES on both branches and rapid IR/MODE
changes using sustained audio. Listen for the dip and any remaining clicks.
Finally8-slot bank and amp chain; reduce FIR/active branches if crackling occurs.
No claim of dynamic cost budgeting, sample-perfect output or device parity.

## Русский / Українська

Локальный кандидат: большие таблицы убраны; обученный RESO остаётся управляемым,
Presence свободно обучается, общий PRES добавляется отдельно. `128+8` даёт9BQ.
При OFF — стандартные RESO/PRES. Короткий fade гасит выход перед сменой IR/MODE.
Три тестовых экспорта получили пользовательский функциональный PASS 2026-09-27.
Подробный протокол и запас DSP в цепях ещё не измерены; другие банки проверяем отдельно.

Локальний кандидат: великі таблиці прибрано; навчений RESO залишається керованим,
Presence вільно навчається, спільний PRES додається окремо. `128+8` дає9BQ.
Для OFF — стандартні RESO/PRES. Короткий fade приглушує вихід перед зміною IR/MODE.
Три тестові експорти отримали користувацький функціональний PASS 2026-09-27.
Докладний протокол і запас DSP у ланцюжках ще не виміряні; інші банки перевіряємо окремо.
