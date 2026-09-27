# Limits and technical details

**English** · [Русский](../ru/technical.md) · [Українська](../uk/technical.md)

[Home](../../README.md) · [Installation, updates and removal](installation.md) · [Prepare IRs and build a bank](workflow.md)

These are the current limits and the boundaries of my tests. A successful export is not a promise that every pedal chain will run without artifacts.

## IR length and DSP load: read before use

The compilation-based builder supports IRs up to **4096 samples at 44.1 kHz,
with 16-bit (Q15) FIR coefficients**. In my pedal experiments, a
4096-tap convolution was already close to the practical DSP ceiling, especially
when combined with other effects. This is not a universal measured CPU limit.
Long IRs also consume more coefficient storage, sharply reducing how many
different IRs fit in a bank. Bank capacity and real-time DSP load are separate limits.

The current compiler-free candidate uses the **HVB4RBJ variable bank** described
below. It rejects a 4096-tap bank under its conservative byte budget, even though
the bank format supports that length. The old HYBRID4 fixed-template CLI remains
available separately (2048 taps per slot, a shared pool of 4096 distinct taps).

**The effect deliberately declares a low, fixed DSP cost (20), not its worst-case
load. This number is not a CPU percentage.** Actual processing load varies with
the selected IR length, filters and active branches; the declared cost does not
track those changes. The pedal may therefore accept a chain that overloads its
DSP without displaying **DSP Full**.

Check the complete chain **by ear**, including the heaviest settings you intend
to use. If clicks, crackling or digital breakup appear, reduce the processing
load: select a shorter IR or switch to **L** or **R** mode so only one processing
branch runs. Selecting IR **OFF** removes its FIR/correction processing but leaves
RESO/PRES and output processing active; it is not a complete branch shutdown.
These artifacts can have other causes too. A clean listening test is a practical
check, not proof of sample-perfect operation or guaranteed DSP headroom.

## Template capacity

HVB4RBJ caps `.text + .audio + .const` at **28,904 bytes** and `.fardata` at
144 bytes; service-table sizes cannot grow. This is a conservative rule for this
template, not a universal Zoom limit. Its code occupies 22,720 bytes, leaving
6,184 bytes for `.const`, including a 1,672-byte prefix. There are no PRES/RESO
coefficient tables: RBJ computes coefficients on control updates. Storage is
244 bytes for the gain LUT, 12 shared PRES parameter bytes and 12 RESO bytes
inside each existing 48-byte descriptor. Nominal RESO retains compensation;
OFF uses 110 Hz/Q 0.7/gain 0.

The format allows 1–8 active slots plus OFF, FIR up to 4096 taps and up to 32 BQ
per model, including RESO/PRES. Actual capacity is determined by the byte budget
and alignment. Three HVB4RBJ test exports (HBUNIT, HB9BQ and eight-slot HB8RBJ)
received a user-reported functional PASS on MS-70CDR on 2026-09-27. This does not
measure DSP headroom; each new bank needs a pedal check. Fewer slots do not
themselves promise smaller state allocation.

Page 2 is `RESO | IR-L | PRES`; page 3 is `RESO | IR-R | PRES`.
IR/MODE changes use 64-sample fade-out before
commit/reset and 128-sample fade-in, without double convolution. A short volume
dip is expected; this is not a seamless crossfade. Presets from the previous parameter order
are not position-compatible: use a new effect ID. The legacy developer build
and fixed-template CLI retain their previous order.

The patcher adjusts bank data, references/relocations, selector maxima, names,
ID and artwork without compiling a new algorithm. Slot labels store up to
7 characters; use at most 5 for display. The display name stores 12 characters;
it does not redraw the title baked into the PNG. Replacement 128×64 monochrome
artwork must fit **848 RLE bytes**. Unknown template hashes and overflowing banks
are rejected before output. Export for Zoom Effect Manager uses RGBA 128×96 and
an uppercase `.ZDL` extension in `inDeviceFileName`.

## Limits and evidence

I tested earlier prototypes on MS-70CDR. Each new bank still
needs device testing: host tests do not establish pedal CPU load or ABI parity.
The developer builder accepts 1–8 active slots, but this is a software envelope, not a
hardware slot guarantee. Its older 22 KiB `.const` warning is a heuristic,
not the HVB4RBJ export gate. No universal 32 KiB ZDL limit or dynamic DSP-budget guarantee is
claimed. The included bank is a synthetic unit impulse, not a commercial IR.

## Source, tests and licenses

Trainer and research-created SDK/effect code use MIT. The linker, container
reader and RLE encoder derive from
[repeat98/ZoomMultistompZDL](https://github.com/repeat98/ZoomMultistompZDL), whose
README declares MIT for repository code. Full notices, upstream references
and modifications are in `THIRD_PARTY_NOTICES.md`, `licenses/` and
`UPSTREAM_PROVENANCE.json`. A link alone does not replace license notices.
Zoom stock code and user IRs are not covered by the project's MIT license;
check your rights before redistributing generated effects containing them.

Zoom firmware, stock effects, stock-derived runtime code, and third-party
reference materials remain the property of their respective rights holders.
They are used in this project for interoperability and reverse-engineering
research. This project is independent and is not affiliated with or endorsed
by Zoom Corporation or Texas Instruments. These notices do not grant a new
license to third-party materials.

The inherited linker includes a 200-byte entry-function template identified
by upstream as copied from NoiseGate (`_DLL_WORDS`); it is adapted when linking.
The separate LineSel, float-division and ABI attribute blobs are obtained from
user-provided files during developer setup. The supplied experimental template
contains their compiled bytes. Excluding separate `.bin` files does not mean
the source package contains no stock-derived material. See `THIRD_PARTY_NOTICES.md`.

`PUBLICATION_MANIFEST.json` hashes the supplied files. From `irbq_lab`, run
`python -m unittest discover -s tests -v` in an environment with dependencies
installed and a desktop display available. Private-model/ZDL fixture tests
skip when absent. The manifest detects corruption; it is not a digital signature.

---

[Home](../../README.md) · [Installation, updates and removal](installation.md) · [Prepare IRs and build a bank](workflow.md)
