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

**The bundled compiler-free HYBRID4 template is limited to 2048 taps per slot**
and a shared pool of 4096 distinct taps. Its pool size does not mean that it can
accept one 4096-tap IR. That requires a different compiled build/template.

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

The experimental HYBRID4 template accepts 1–4 active slots plus OFF, at most
2048 FIR taps per slot, a shared pool of 4096 distinct Q15 taps (identical FIRs
are shared), and up to 30 correction biquads plus RESO/PRES per slot.
Unused slots are padded with bypass descriptors. State allocation stays fixed;
fewer slots do not reduce the template's reserved state memory.
Only bank data, slot labels (7 characters stored; use at most 5 for display), the 12-character display name, ID,
IR selector maxima and card bitmap can change. Code, pointers and relocations
remain byte-identical. Internal ELF names stay unchanged. A new display name
does not redraw the title baked into the PNG. Replacement 128x64 monochrome
artwork must encode to at most 848 bytes; larger images are rejected.
Template version/hash mismatches and overflowing banks are rejected before output.
This template needs a fresh pedal test; earlier prototype tests do not validate it.

## Limits and evidence

I tested earlier prototypes on MS-70CDR. Each new bank still
needs device testing: host tests do not establish pedal CPU load or ABI parity.
The developer builder accepts 1–8 active slots, but this is a software envelope, not a
hardware slot guarantee. The 22 KiB `.const` warning is a conservative
heuristic. No universal 32 KiB ZDL limit or dynamic DSP-budget guarantee is
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
