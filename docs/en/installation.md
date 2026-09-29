# Installation, updates and removal

[English](installation.md) · [Русский](../ru/installation.md) · [Українська](../uk/installation.md)

## Choose your download

Download an application asset from [Releases](https://github.com/Leemuzhko/HYBRID-IR/releases), not GitHub's **Source code (zip)** or **Code → Download ZIP**.

- **Standalone (recommended):** includes Python 3.14, Tcl/Tk and dependencies. No separate Python installation or internet is needed during installation or normal use.
- **Lite:** smaller download; requires [official Windows x64 Python 3.14](https://www.python.org/downloads/windows/) with Tcl/Tk and the `py` launcher. Setup downloads pinned packages from PyPI into a private `.venv`; it does not modify your global packages.

Both flavors contain the same application and templates for their source revision. Lite is smaller to download, not necessarily much smaller after installation. Development releases are experimental; packaging tests do not prove pedal compatibility. While a repository is private, GitHub access is required.

## Install

1. Extract the **complete** ZIP into a separate folder.
2. Run **Install_HYBRIDIR.cmd**. Choose a new installation folder and optionally create a desktop shortcut.
3. Leave **Developer: enable TI compilation** unchecked for normal use. Click **Install / Update**.
4. Launch **Start_HYBRIDIR.cmd** from the installed folder or use its desktop shortcut.

These are ZIP packages with a Windows setup wizard, not signed EXE/MSI installers. Standalone launches its bundled interpreter directly; it does not register Python or change PATH. No administrator rights are required for a writable per-user destination.

Stable defaults to `%LOCALAPPDATA%/HYBRIDIR`; development to `%LOCALAPPDATA%/HYBRIDIR-Development`, with a separate shortcut and preferences. Library folders remain user-selected. Keep IRs, banks and projects outside application/runtime folders.

## Update safely

Close HYBRID IR. Extract the new archive **outside** the existing installation, run its installer, choose the existing folder and confirm the update. Use the **same flavor and channel**. To change Lite/Standalone or stable/development, install in a separate folder; existing files are not overwritten.

The updater prepares and checks a candidate, preserves the complete old installation in a sibling backup, then installs at the final path. Personal files are retained; modified application code stays in the backup and is not reused. Lite prepares fresh environments and downloads dependencies; Standalone copies the bundled runtime offline. Both need extra disk space. Backup and candidate folders are deliberately retained: remove them manually only after checking the new version and your files.

If preparation fails, the old installation remains. Later failures attempt rollback. If `<folder>.update.json` remains, close all instances and follow its recovery paths: preserve a failed candidate, restore the named backup, and remove the journal only after recovery. Do not blindly delete the installation or repeat setup over an incomplete folder.

Legacy installs without an ownership receipt require a new folder. The installer may refuse an update if Windows cannot verify that Python/application processes are closed. Check `installation.log` when present.

## Uninstall

Run **Uninstall_HYBRIDIR.cmd** inside the installed folder after closing the app.

Lite uses the separately installed Python. Standalone copies its verified Python/Tk uninstall runtime to a temporary folder, runs deletion from there to avoid DLL locks, and cleans that temporary folder after exit. Neither needs a TI compiler.

Only recorded, unchanged application files and private venv/cache files are removed. New or modified personal files are preserved; therefore the installation folder may remain. The owned desktop shortcut is removed only if unchanged. Settings removal is optional. User IRs, projects, banks, exports, other versions and update backups are not automatically erased. There is currently no Windows Installed Apps registration.

If files are locked or changed, read the result and retry after closing the app. Do not remove a parent folder containing other projects. Python installed separately for Lite and TI remain available to other programs.

## Developer compilation

Training and **Patch ZDL (no TI)** need no TI compiler. **Build ZDL** is optional: enable the Developer checkbox and supply TI C6000 CGT 8.5.0.LTS and the required user-owned donor files. Neither compiler nor donor blobs are included. This distribution does not change the ZDL template or claim new hardware validation.

For an installation named `APP`, recovery uses `APP.update.json` and an `APP.backup-…` sibling. A custom `IRBQ_SETTINGS_PATH` is never removed automatically; preserve or remove that file yourself.

[Prepare IRs and banks](workflow.md) · [Technical limits](technical.md)
