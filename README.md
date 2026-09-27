<p align="center">
  <img src="assets/IR_CAB-1200x800.png" width="240" alt="HYBRID IR — dual-channel cabinet effect card">
</p>
<h1 align="center">HYBRID IR</h1>
<p align="center"><strong>Your cabinet sound. Inside your Zoom.</strong><br>
Prepare cabinet responses, fit hybrid FIR/IIR models and build your own ZDL effects.</p>
<p align="center">
  <img src="https://img.shields.io/badge/Desktop-Windows-2563eb?style=flat-square" alt="Desktop: Windows">
  <img src="https://img.shields.io/badge/DSP-FIR_%2B_IIR-475569?style=flat-square" alt="DSP: FIR + IIR">
  <img src="https://img.shields.io/badge/Patcher-No_TI_compiler-475569?style=flat-square" alt="Patcher: no TI compiler">
  <img src="https://img.shields.io/badge/Status-Experimental-92400e?style=flat-square" alt="Status: experimental">
</p>
<p align="center"><strong>English</strong> · <a href="README.ru.md">Русский</a> · <a href="README.uk.md">Українська</a></p>
<h3 align="center"><a href="https://github.com/Leemuzhko/HYBRID-IR/archive/refs/heads/main.zip">Download for Windows</a></h3>
<p align="center"><a href="#installation">Installation</a> · <a href="#workflow">Build your first effect</a> · <a href="https://ko-fi.com/leemuzhko">Support on Ko-fi</a></p>
<p align="center">MS-50G · MS-60B · MS-70CDR · G1on · G1Xon · B1on<br>
<sub>Project device family. Hardware validation varies by model and bank; see limits below.</sub></p>

---

Fit your cabinet impulse responses in IRBQ Trainer and build a HYBRID IR ZDL
with your own bank, slot names, effect name, ID and card image. This builder
targets the HYBRID IR effect; it does not turn arbitrary stock effects into
IR loaders. Hardware reference for the documented prototype tests: Zoom MS-70CDR,
firmware 2.10. The broader device family above is not a claim that every model
and every generated bank has been hardware-validated.

## What is HYBRID IR, and why use it?

A cabinet impulse response (IR) describes how a cabinet/microphone setup
filters a signal. A conventional IR loader reproduces that response using
convolution with the stored samples. Longer direct FIR filters require more
work per audio sample, which matters on a pedal with a limited DSP budget.

HYBRID IR combines a **FIR filter** with a **chain of biquad (IIR) filters**.
The idea is to let efficient biquads reproduce part of the cabinet's response,
leaving a shorter FIR to handle the remaining detail. This can offer a useful
accuracy/CPU trade-off instead of spending the whole budget on a long FIR.
Savings depend on FIR length, biquad count and the other effects in the chain;
there is no universal performance or sound-equivalence guarantee.

The desktop **IRBQ Trainer** fits this model to your WAV, lets you compare
responses and audition the result, and exports the prepared model. “Training”
here means numerical filter fitting on the computer, not a neural network
running in the pedal. The **ZDL Patcher** packages your selected models into
one effect with selectable slots. The pedal runs the prepared filters and
provides routing, output level, presence and resonance controls.

This is useful when you want your own cabinet sounds alongside an amp effect
on a resource-limited MultiStomp. A fitted hybrid model is an **approximation**:
matching a magnitude response does not alone establish identical phase,
transients or sound. Compare and listen before exporting, then test the pedal
chain. This is cabinet filtering, not an amp/distortion model or a claim that
all long IRs can be replaced transparently. Importing a WAV directly into a
bank does not automatically perform hybrid fitting; prepare it in Trainer first
when you want that trade-off.

## IR length and DSP load: read before use

The compilation-based builder supports IRs up to **4096 samples at 44.1 kHz,
with 16-bit (Q15) FIR coefficients**. In the author's pedal experiments, a
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

## Download — experimental Windows distribution

[Download Trainer + ZDL Patcher for Windows (ZIP)](https://github.com/Leemuzhko/HYBRID-IR/archive/refs/heads/main.zip)

This development snapshot includes the source, `.cmd` installer, dependencies list
and precompiled HYBRID4 template. It is a **source-based distribution, not a
standalone EXE**, and contains no commercial cabinet IRs. The link follows
the main branch, not a versioned release. Keep your downloaded archive for reproducibility.
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

<a id="installation"></a>

## Install on Windows

1. Install [official 64-bit Python 3.14](https://www.python.org/downloads/windows/)
   with **Tcl/Tk** and the **Python launcher** (`py`). If Python is missing,
   `Install_HYBRIDIR.cmd` opens the download page; it does not install Python.
2. Download the ZIP above, use **Extract All**, and open the extracted folder
   containing `Install_HYBRIDIR.cmd`. Do not launch it from inside the ZIP.
3. Double-click **Install_HYBRIDIR.cmd** and choose a new installation folder.
   Leave **Developer: enable TI compilation** unchecked; TI and donor fields
   only appear when enabled. Select **Create a desktop shortcut** if desired
   (enabled by default). Click **Install / Update** and wait for completion.
   Internet is needed to download Python packages from PyPI into the app's
   private environment; HYBRID IR itself does not require administrator rights.
4. Open **Start_HYBRIDIR.cmd** in the installation folder, not the ZIP folder.
   Or use the **HYBRID IR** desktop shortcut with the supplied pedal icon.
   An existing shortcut is preserved, not overwritten. Source files and notices remain
   accessible in the installation.

If setup fails, check `installation.log` in the destination when present.
For a failed fresh installation, retry in a **new folder**. For an existing
installation with an uninstall receipt, use the update procedure below.
Keep exported models and bank projects before changing versions.

For developer compilation only, install [TI C6000 CGT 8.5.0.LTS](https://www.ti.com/tool/C6000-CGT)
and select the Developer checkbox, compiler folder and stock folder in Setup.
No full CCS IDE is needed. Developer setup can later be made in a new folder.
Prerequisite errors are shown before copying files. Errors after copying may
leave a partial folder; `installation.log` is created when dependency installation
starts. Existing installations require the explicit update confirmation below.
Standard setup enables **Patch ZDL (no TI)** and disables the developer **Build ZDL** button.
During a ZDL build, wait for completion before closing the application.

The installer is a source/Tk setup wizard launched by `.cmd`, not a standalone
signed `.exe`. Python remains a first-time prerequisite; TI is optional.

## Updating an existing installation

Download and extract the new package **outside** your installed application.
Close HYBRID IR, run the new `Install_HYBRIDIR.cmd`, choose the existing app
folder and click **Install / Update**. The confirmation shows current/new bundle
identifiers and how many application files have local modifications. Bundle IDs
identify exact packages; they are not semantic version numbers or signatures.
Existing Developer mode and compiler settings are retained during an update;
the Setup Developer fields apply only to a new installation.

The updater prepares and checks a separate candidate first. It then keeps the
entire old installation in a sibling `APP.backup-*` folder and installs a fresh
Python environment at the original path. This takes extra disk space and performs
dependency installation twice; internet may be required for both passes.
Personal IRs, banks, projects and exports are copied back without being enrolled
as application-owned files. Shared preferences are not changed. Modified program
files stay in the backup; the new version uses its own program files. If a personal
file conflicts with a new application path, the update is rejected, not overwritten.
Existing desktop shortcuts remain at the same target; modified shortcuts are not replaced.

An ordinary failure during replacement restores the old folder. If rollback is
blocked or power/process termination interrupts replacement, a sibling
`APP.update.json` journal identifies the backup and recovery instructions.
Close all app/setup processes before recovery; preserve the candidate folder,
restore the backup to the original path, then remove the journal only after
checking recovery. A pending journal blocks launch and lifecycle operations.
Do not delete the backup merely to silence an error.

Backup, `APP.staging-*` and failed-candidate `APP.failed-*` folders are retained
for inspection, not automatically cleaned or removed by uninstall. After checking
the updated app and your data, you may manually remove only those identified
folders. Do not run the old backup in its renamed location: restore its original
path first. Installations without receipts, incomplete installations and linked
paths require a new installation folder or manual recovery instead of update.

## Uninstall

Run **Uninstall_HYBRIDIR.cmd** from the installation folder. It uses system
Python 3.14, not the private environment being removed. Close the application
first, review the file counts, and confirm removal. No Windows Installed apps
entry is registered in this version.

The uninstaller removes recorded application files, its private `.venv` and
`.test-cache`, and the unchanged desktop shortcut it created. New personal
files and modified application sources are preserved. Do not store personal
files inside the private environment/cache directories. If files are preserved,
the installation folder remains and the result dialog says so. Shared IRBQ Lab
language/theme settings are removed only if you tick the separate checkbox;
it is off by default. ZEM folders and exported effects outside the installation
are never deleted. A custom `IRBQ_SETTINGS_PATH` is left untouched.

If a locked file prevents removal, close the application and retry. Older
installations without an uninstall receipt cannot use this uninstaller: do not
copy it into an old installation and guess ownership. Use the manual fallback:

1. Close HYBRID IR and wait for any training/export operation to finish.
2. Move any personal WAVs, models, bank projects and exported ZDLs stored inside
   the installation folder to a safe location.
3. Delete only the folder you selected when installing HYBRID IR. It contains
   the application and its private `.venv` environment. Do not delete a parent
   folder containing other applications or documents.
4. Delete the **HYBRID IR** desktop shortcut if you created one.
5. Optionally remove `%APPDATA%\IRBQ_Lab\settings.json` to reset language/theme
   preferences. This file is shared with other IRBQ Lab installations; keep it
   if you still use one. A custom `IRBQ_SETTINGS_PATH` overrides that location.

Do not uninstall system Python or TI merely to remove this app; other programs
may use them. Leave your Zoom Effect Manager custom-effects folder and its ZDLs
untouched. Removing the desktop app does not remove an effect already installed
on the pedal; manage pedal effects separately in Zoom Effect Manager.

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

<a id="workflow"></a>

## Everyday workflow

1. Load your WAV in Trainer and fit the response, or open a prepared Trainer model.
2. Open **Zoom ZDL**. Use **Current model** or import Trainer JSON exports;
   arrange the bank and set the slot labels, effect name and ID.
3. Select **ZEM custom ZDL folder**: the same folder you configured in Zoom
   Effect Manager to read custom effects, not necessarily your export folder.
   Bundled reserved IDs are always checked; no stock ZDL folder is needed.
   Resolve any
   conflict before exporting, then save the bank project for later editing.
4. Click **Patch ZDL (no TI)** and choose an output folder. **Build ZDL** is the
   optional developer compiler path, not the button needed for normal use.
5. Keep the generated `.patch.json` report alongside the `.zdl`. Install the
   effect using **Zoom Effect Manager**, as described below, then test it on the pedal.
   The app does not flash devices.

## Install the ZDL on the pedal — Zoom Effect Manager required

Use [Zoom Effect Manager (download)](https://zoomeffectmanager.com/en/download/)
to install the generated HYBRID IR `.zdl` on the pedal. This is the required
transfer tool for the workflow documented here, not an optional part of Trainer.
Trainer/Patcher only creates the file; its installer installs the desktop app,
not the effect on the pedal. Zoom Effect Manager is a separate third-party tool.

Use version **2.3.3 or newer** for reading custom ZDL files from a folder;
the project's release notes introduce that feature in 2.3.3. Put your generated
ZDL in a dedicated folder and use the manager's folder-loading feature, then
follow its instructions for your pedal model to write the effect. Connect the
pedal before starting the manager and restart it after writing, as its download
page instructs. Back up your presets first and do not disconnect USB or power
during writing. Installing a file does not establish its DSP/RAM safety.

English/dark is the default; language and theme controls are in the toolbar.

The custom folder is scanned recursively by ZDL header identity (GID + FXID),
not filename. It is saved with the bank project. The output folder is chosen
separately; exporting elsewhere does not add the effect to ZEM's folder automatically.
Reserved identities cannot be replaced, even with a matching name. Custom
same-name/ID replacements require confirmation; conflicting names get a free-ID
suggestion. The bundled catalog is a collection snapshot, not a live inventory
of the pedal or a guarantee against future IDs.
It reserves 255 identities from 450 ZEM original-effect files, including the
bundled Other effects RainSel, RTFM and Div0 (stored under Filter in that collection).
Source filenames and SHA-256 hashes are retained in `irbq_lab/irbq/stock_ids.json`;
no donor ZDL files are bundled with the catalog.

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

## Support the project

HYBRID IR is free to use. If it helps you create your sound, you can
[support development on Ko-fi](https://ko-fi.com/leemuzhko).
Voluntary support helps fund development, testing and documentation.
No payment is required to use the tools; support does not purchase features,
priority assistance or a commitment to a release date.

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
