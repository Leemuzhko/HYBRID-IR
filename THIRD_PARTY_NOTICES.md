# Third-party code and provenance

English | [Українська](THIRD_PARTY_NOTICES.uk.md)

Original HYBRID IR project code is MIT; third-party exceptions are listed below.
Keep this file and `licenses/` with source and
binary distributions. These notices do not license user IRs or stock Zoom code.

## ZoomMultistompZDL — repeat98 and contributors

Upstream: https://github.com/repeat98/ZoomMultistompZDL

Pinned reference: `4ec75eea32971f4cb7c76d96e2020908888dbfc2`.
The README explicitly declares repository code MIT unless a file says otherwise:
https://github.com/repeat98/ZoomMultistompZDL/blob/4ec75eea32971f4cb7c76d96e2020908888dbfc2/README.md#license

Included derivatives:

- `hybridir_sdk/build/linker.py`: custom static linker, extended locally for the
  researched control/state ABI and HYBRID IR. Its upstream header credits an
  earlier `airwindowsZoom` implementation; a separate v1 repository was not
  established, so the verified attribution is to this pinned upstream.
- `hybridir_sdk/build/screen_image.py`: canvas/RLE encoder, with local control
  rendering and long-run RLE fixes.
- `hybridir_sdk/build/zdl.py`: container reader/writer, text matches the pinned
  upstream (line-ending-independent comparison).

The upstream tree supplies its MIT declaration in README, without a separate
LICENSE file. `licenses/ZoomMultistompZDL-MIT.txt` retains that declaration,
author attribution and the standard MIT permission text. No copyright year
or original notice absent from upstream is invented.

## Zoom Firmware Editor — Barsik-Barbosik

https://github.com/Barsik-Barbosik/Zoom-Firmware-Editor

`zdl.py` credits `EffectType.java` for the category mapping. The upstream
LICENSE.md is retained verbatim in `licenses/Zoom-Firmware-Editor-MIT.txt`,
including its original copyright wording. No editor binaries or icons are
included.

## Research-created project code

`sdk/build_effect.py`, `sdk/include/zoom_sdk.h`,
`sdk/include/zoom_materialize_init.h`, `build/zdl_smoke.py` were introduced in
the user's research repository at `f4030cf` (Leemuzhko); `build/toolchain.py`
at `bcf94ad`. These are project code, not TI's or Zoom's official SDK.
Trainer, bank authoring, HYBRID IR effect/kernel and installation code are
project code. Existing application attribution remains in `irbq_lab/LICENSE.txt`.
The card artwork was supplied by the project author. Filter equations refer
to the W3C Audio EQ Cookbook: https://www.w3.org/TR/audio-eq-cookbook/

## Separately installed components

Python and pip dependencies keep their own licenses in their installations.
This source installer downloads Python packages into a private environment;
it does not redistribute their installed binaries. TI C6000 CGT is obtained
separately from Texas Instruments: https://www.ti.com/tool/C6000-CGT

The three separate runtime blobs (`linesel_handlers.bin`, `divf_rts.bin`,
`c6xabi_attributes.bin`) are provisioned locally from matching user files,
checked against known hashes, and excluded as binary files from this distribution.
Their reference donors are LineSel, ANA234CH and Exciter respectively.

The inherited `hybridir_sdk/build/linker.py` also contains `_DLL_WORDS`, a
200-byte entry-function template explicitly described by upstream as a copy
from NoiseGate. It remains included as a numeric array; linking adapts its
descriptor count and addresses. This is stock-derived material embedded in
source, not independently authored project code. This attribution is based
on the upstream comment/history, not a new byte comparison with NoiseGate.

Zoom firmware, stock effects, stock-derived code and third-party reference
materials remain the property of their respective rights holders and are
used for interoperability and reverse-engineering research, following the
distinction in the upstream README's License section. HYBRID IR is independent
and is not affiliated with or endorsed by Zoom Corporation or Texas Instruments.
Neither the repository MIT declaration nor these notices grant
rights to redistribute Zoom firmware or stock-effect code. No commercial IR
or fitted commercial cabinet model is included.

The experimental `hybridir_sdk/templates/HYBRID4.zdl` is a compiled template
with synthetic unit impulses and the inherited stock-derived runtime described
above. It is included for interoperability and reverse-engineering research;
the project's MIT license does not relicense those embedded third-party portions.
It is not a wholly original/MIT-only binary. Its hash and fixed patch regions
are documented in the accompanying HYBRID4.json. New hardware validation is pending.
