# Installation, updates and removal

**English** · [Русский](../ru/installation.md) · [Українська](../uk/installation.md)

[Home](../../README.md) · [Prepare IRs and build a bank](workflow.md) · [Limits and technical details](technical.md)

I recommend starting with the standard installation. TI compilation is an optional developer path, not a requirement for patching your IRs.

## Download — experimental Windows distribution

[Download Trainer + ZDL Patcher for Windows (ZIP)](https://github.com/Leemuzhko/HYBRID-IR/archive/refs/heads/main.zip)

This development snapshot includes the source, `.cmd` installer, dependencies list
and precompiled HVB4RBJ template (plus the legacy HYBRID4 CLI template). It is a **source-based distribution, not a
standalone EXE**, and contains no commercial cabinet IRs. The link follows
the main branch, not a versioned release. Keep your downloaded archive for reproducibility.
While the repository is private, sign in to a GitHub account with repository
access before downloading. A 404 can mean that access is missing.

Trainer 0.4.0 includes the variable-bank patcher, trained RESO/common PRES,
switching fades and portable authoring library. Three HVB4RBJ test exports
worked on MS-70CDR; test your own bank and full effect chain.

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

The legacy-process check is deliberately conservative: other Python programs
started through `launch.py` or `run.py` may also need to be closed. If Windows
denies process inspection, the update stops without replacing the installation.

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
it is off by default. Zoom Effect Manager folders and exported effects outside the installation
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

---

[Home](../../README.md) · [Prepare IRs and build a bank](workflow.md) · [Limits and technical details](technical.md)
