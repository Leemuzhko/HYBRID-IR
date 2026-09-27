# HYBRID IR

Fit your cabinet impulse responses in IRBQ Trainer and build a HYBRID IR ZDL
with your own bank, slot names, effect name, ID and card image. This builder
targets the HYBRID IR effect; it does not turn arbitrary stock effects into
IR loaders. Primary hardware target: Zoom MS-70CDR, firmware 2.10.

## Install on Windows

1. Install official **64-bit Python 3.14 with Tcl/Tk**. If it is missing,
   `Install_HYBRIDIR.cmd` opens the Python download page.
2. Extract this archive and double-click **Install_HYBRIDIR.cmd**. Choose a new
   installation folder. Leave the **Developer** option unchecked; no compiler
   or stock files are needed for the template patcher.
   Click **Install**. Internet is used to install Python packages into a private
   environment; no administrator privileges are required for HYBRID IR.
3. Start **Start_HYBRIDIR.cmd** in the installed folder. A shortcut to this file
   can be placed on your desktop. Source files and notices remain accessible.

For developer compilation only, install [TI C6000 CGT 8.5.0.LTS](https://www.ti.com/tool/C6000-CGT)
and select the Developer checkbox, compiler folder and stock folder in Setup.
No full CCS IDE is needed. Developer setup can later be made in a new folder.
Prerequisite errors are shown before copying files. Errors after copying may
leave a partial folder; `installation.log` is created when dependency installation
starts. Existing installations are never overwritten by this first version.
Standard setup enables **Patch ZDL (no TI)** and disables the developer **Build ZDL** button.
During a ZDL build, wait for completion before closing the application.

The installer is a source/Tk setup wizard launched by `.cmd`, not a standalone
signed `.exe`. Python remains a first-time prerequisite; TI is optional.

## Stock files: developer setup only

Provide your own stock ZDL folder containing matching **LineSel**, **ANA234CH**
and **Exciter** versions. The reference filenames are `MS-70CDR_LINESEL.ZDL`,
`ANA234CH.ZDL`, `MS-70CDR_EXCITER.ZDL`. Renamed copies are accepted when the
extracted bytes match. Subfolders are searched. Setup extracts only three
small required fragments and verifies their SHA256 values. An existing local
runtime folder with the matching `.bin` files also works.

The installer does not download firmware, alter the input files, or access a
pedal. Separate stock blob files and the TI compiler are not bundled; the
precompiled template does contain inherited stock runtime. Other donor revisions
fail with a precise missing-file message rather than guessing code offsets.
The exact recipes and hashes are in `hybridir_sdk/sdk/runtime_setup.py`.

## Everyday workflow

Load your WAV in Trainer, fit the response and export a model. In the **Zoom**
tab, use **Current model** or import Trainer JSON exports, assemble the bank,
choose the name/ID, and click **Patch ZDL (no TI)**. Use Zoom Effect Manager separately
to transfer the resulting effect to the pedal. The app does not flash devices.
English/dark is the default; language and theme controls are in the toolbar.

The experimental HYBRID4 template accepts 1–4 active slots plus OFF, at most
2048 FIR taps per slot, a shared pool of 4096 distinct Q15 taps (identical FIRs
are shared), and up to 30 correction biquads plus RESO/PRES per slot.
Unused slots are padded with bypass descriptors. State allocation stays fixed;
fewer slots do not reduce the template's reserved state memory.
Only bank data, 7-character slot labels, the 12-character display name, ID,
IR selector maxima and card bitmap can change. Code, pointers and relocations
remain byte-identical. Internal ELF names stay unchanged. A new display name
does not redraw the title baked into the PNG. Replacement 128x64 monochrome
artwork must encode to at most 848 bytes; larger images are rejected.
Template version/hash mismatches and overflowing banks are rejected before output.
This template needs a fresh pedal test; earlier prototype tests do not validate it.

## Limits and evidence

Earlier prototypes were tested by the author on MS-70CDR. Each new bank still
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
