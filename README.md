# HYBRID IR

![HYBRID IR effect card with left and right channel controls](assets/IR_CAB-1200x800.png)

Fit your cabinet impulse responses in IRBQ Trainer and build a HYBRID IR ZDL
with your own bank, slot names, effect name, ID and card image. This builder
targets the HYBRID IR effect; it does not turn arbitrary stock effects into
IR loaders. Primary hardware target: Zoom MS-70CDR, firmware 2.10.

## Download — experimental Windows distribution

[Download Trainer + ZDL Patcher for Windows (ZIP)](https://github.com/Leemuzhko/HYBRID-IR/archive/255a300f96a70b20c3d87e0a38daf1bbbfc95ecc.zip)

This pinned snapshot includes the source, `.cmd` installer, dependencies list
and precompiled HYBRID4 template. It is a **source-based distribution, not a
standalone EXE**, and contains no commercial cabinet IRs. The link stays on
the initial patcher version (`255a300`); it does not track development changes.
While the repository is private, sign in to a GitHub account with repository
access before downloading. A 404 can mean that access is missing.

The fixed template is experimental and still needs a fresh pedal test.
Do not treat this download as a hardware-validated release.

## What the patcher does

Trainer fits your cabinet response; the integrated **Zoom ZDL** tab assembles
the resulting models into a HYBRID IR effect. **Patch ZDL (no TI)** writes the
bank and supported metadata into the bundled, verified template without
recompiling DSP code. You do not need the TI compiler or stock donor files.

You can select the bank contents, rename slots and the effect, choose its ID,
and supply a compatible card bitmap. The patcher validates template identity
and capacity before writing a `.zdl` and a `.patch.json` report. It does not
modify arbitrary ZDL effects or upload anything to the pedal.

## Install on Windows

1. Install [official 64-bit Python 3.14](https://www.python.org/downloads/windows/)
   with **Tcl/Tk** and the **Python launcher** (`py`). If Python is missing,
   `Install_HYBRIDIR.cmd` opens the download page; it does not install Python.
2. Download the ZIP above, use **Extract All**, and open the extracted folder
   containing `Install_HYBRIDIR.cmd`. Do not launch it from inside the ZIP.
3. Double-click **Install_HYBRIDIR.cmd** and choose a new installation folder.
   Leave **Developer: enable TI compilation** unchecked and leave the TI and
   stock-folder fields empty. Click **Install** and wait for completion.
   Internet is needed to download Python packages from PyPI into the app's
   private environment; HYBRID IR itself does not require administrator rights.
4. Open **Start_HYBRIDIR.cmd** in the installation folder, not the ZIP folder.
   You can make a desktop shortcut to it. Source files and notices remain
   accessible in the installation.

If setup fails, check `installation.log` in the destination when present.
Retry in a **new folder**: this installer does not update or overwrite existing
installations. Keep exported models and bank projects before changing versions.

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

1. Load your WAV in Trainer and fit the response, or open a prepared Trainer model.
2. Open **Zoom ZDL**. Use **Current model** or import Trainer JSON exports;
   arrange the bank and set the slot labels, effect name and ID.
3. Select your stock/Patched folders for ID-conflict checks. Resolve any
   conflict before exporting, then save the bank project for later editing.
4. Click **Patch ZDL (no TI)** and choose an output folder. **Build ZDL** is the
   optional developer compiler path, not the button needed for normal use.
5. Keep the generated `.patch.json` report alongside the `.zdl`. Use Zoom
   Effect Manager separately to transfer the effect and test it on your pedal.
   The app does not flash devices.

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
