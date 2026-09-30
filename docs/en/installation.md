# Installation, updates and removal

[English](installation.md) · [Русский](../ru/installation.md) · [Українська](../uk/installation.md)

[Windows](#windows) · [macOS 15+](#macos) · [Mac troubleshooting](#macos-troubleshooting)

<a id="windows"></a>

## Windows x64 — choose your download

Download an application asset from [Releases](https://github.com/Leemuzhko/HYBRID-IR/releases), not GitHub's **Source code (zip)** or **Code → Download ZIP**.

- **Standalone (recommended):** includes Python 3.14, Tcl/Tk and dependencies. No separate Python installation or internet is needed during installation or normal use.
- **Lite:** smaller download; requires [official Windows x64 Python 3.14](https://www.python.org/downloads/windows/) with Tcl/Tk and the `py` launcher. Setup downloads pinned packages from PyPI into a private `.venv`; it does not modify your global packages.

Windows Lite and Standalone contain the same application and templates for their source revision; the separately added Mac preview is a different snapshot. Lite is smaller to download, not necessarily much smaller after installation. Development releases are experimental; packaging tests do not prove pedal compatibility. While a repository is private, GitHub access is required.

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

**Known issue in the original published Standalone v0.4.1:** removal can fail beneath AppData. The development fix is not included in the existing Windows ZIPs. If removal stops, retain the installation and your files, and report the error; do not delete a shared parent folder. Adding the Mac preview did not replace the Windows packages.

Run **Uninstall_HYBRIDIR.cmd** inside the installed folder after closing the app.

Lite uses the separately installed Python. Standalone copies its verified Python/Tk uninstall runtime to a temporary folder, runs deletion from there to avoid DLL locks, and cleans that temporary folder after exit. Neither needs a TI compiler.

Only recorded, unchanged application files and private venv/cache files are removed. New or modified personal files are preserved; therefore the installation folder may remain. The owned desktop shortcut is removed only if unchanged. Settings removal is optional. User IRs, projects, banks, exports, other versions and update backups are not automatically erased. There is currently no Windows Installed Apps registration.

If files are locked or changed, read the result and retry after closing the app. Do not remove a parent folder containing other projects. Python installed separately for Lite and TI remain available to other programs.

## Developer compilation

Training and **Patch ZDL (no TI)** need no TI compiler. **Build ZDL** is optional: enable the Developer checkbox and supply TI C6000 CGT 8.5.0.LTS and the required user-owned donor files. Neither compiler nor donor blobs are included. This distribution does not change the ZDL template or claim new hardware validation.

For an installation named `APP`, recovery uses `APP.update.json` and an `APP.backup-…` sibling. A custom `IRBQ_SETTINGS_PATH` is never removed automatically; preserve or remove that file yourself.

---

<a id="macos"></a>
## macOS 15+ — Apple Silicon and Intel (preview)

This section describes the macOS preview attached to **v0.4.1**, not the Windows installer. Use the **ARM64** ZIP for Apple Silicon or **x86_64** for Intel. Check **Apple menu → About This Mac** for your chip/processor and macOS version. Older macOS versions are not supported by this preview.

[Download Apple Silicon (ARM64)](https://github.com/Leemuzhko/HYBRID-IR/releases/download/v0.4.1/HYBRID-IR-0.4.1-macOS-arm64-preview.zip) · [Download Intel (x86_64)](https://github.com/Leemuzhko/HYBRID-IR/releases/download/v0.4.1/HYBRID-IR-0.4.1-macOS-x86_64-preview.zip)

Python 3.14.6, Tcl/Tk 9.0.3 and runtime dependencies are included in **HYBRID IR.app**. Do not install Python, Homebrew or the TI compiler for normal use. There is no separate Mac Lite package, and Windows `.cmd`/PowerShell installers are not used.

### Verify and install

1. Download the matching application ZIP and its adjacent `.zip.sha256` file from the same release. Do not use **Source code** as an application installer.
2. Optionally check the archive before opening it. In Terminal, change to the download folder and run the appropriate command below. It must report **OK**. A matching checksum verifies the published bytes, not Apple approval or the absence of malware.
3. Double-click the ZIP in Finder to extract it with Archive Utility. Keep the complete **HYBRID IR.app** bundle intact; do not move files out of it.
4. Drag **HYBRID IR.app** to **Applications** (`/Applications`) or your own `~/Applications` folder. Finder may require permission to write to the shared Applications folder.
5. Open the copied application, not a file inside its bundle. Store personal IRs, banks and projects outside the application.

```sh
cd ~/Downloads
# Apple Silicon — use only the command matching the ZIP you downloaded:
shasum -a 256 -c HYBRID-IR-0.4.1-macOS-arm64-preview.zip.sha256
# Intel:
shasum -a 256 -c HYBRID-IR-0.4.1-macOS-x86_64-preview.zip.sha256
```

### First launch and macOS security

The preview is **ad-hoc signed, not Developer ID signed, and not notarized by Apple**. It may be blocked on first launch. Apple cannot provide its usual notarization assurance for this build.

Only if you trust the source and have checked the archive: try opening the app, then use **System Settings → Privacy & Security → Open Anyway** for **HYBRID IR**, when offered, and confirm the application-specific prompt. Do not disable Gatekeeper globally or remove quarantine recursively as a general installation step. If macOS reports malware, a damaged application or a checksum mismatch, stop and investigate rather than bypassing it. Managed Macs may require administrator approval. See [Apple's current guidance](https://support.apple.com/en-us/102445).

### Check the application

Open **Zoom ZDL**, use **Import WAV**, then **Patch ZDL (no TI)** to export using HIR3A. The Trainer can fit FIR/BQ models; K-weighted modes and saved Preparation defaults are included. Keep source audio and save your project/bank before experimenting. Use [Zoom Effect Manager](https://zoomeffectmanager.com/en/download/) to transfer exported effects: HYBRID IR does not install them on the pedal directly.

Native automated tests covered both architectures, including app startup, data round trips, normalization, defaults, FIR training, GUI and HIR3A export. The maintainer also reported startup of a preview build; this is not a manual validation claim for both architectures. Audible playback, extended use and new effect banks/chains still need real-device checks. [Mac validation record](https://github.com/Leemuzhko/HYBRID-IR/releases/download/v0.4.1/MACOS-VALIDATION-0.4.1.json).

### Settings, library and logs

| Data | Default location |
| --- | --- |
| Preferences and saved Preparation defaults | `~/Library/Application Support/HYBRID IR/settings.json` |
| Cache and startup logs | `~/Library/Caches/HYBRID IR/` |
| Default library | `~/Documents/HYBRID IR/Library/` |
| Other projects, banks and exports | The folders you choose |

In Finder use **Go → Go to Folder** to open these paths. `~` means your home folder. A custom `IRBQ_SETTINGS_PATH` overrides the settings location; preserve that file separately. The app bundle is not a storage location for user data.

### Update or roll back

Quit HYBRID IR, back up your library/projects/banks and `settings.json`, and keep a copy of the previous `.app` outside Applications. Extract the new matching-architecture ZIP separately, verify it, then replace the **whole** `.app` in Applications. Do not merge bundle contents or run Windows update scripts. Preferences and libraries are outside the bundle and remain in place. This preview uses manual replacement, not a Windows-style updater with automatic rollback.

Open the replacement and check your saved defaults and a project. To roll back, quit it and restore the previous `.app`; restore your data backup if a newer version changed data formats. Keep only the intended active app in Applications to avoid launching the wrong copy.

### Uninstall

Quit the app and move **HYBRID IR.app** to Trash. Your library, IRs, projects, banks, exports and settings remain. No Windows uninstaller or separate removal of the bundled Python is needed.

For an optional settings reset, first back up `settings.json`, then rename or move that file while the app is closed. Cache cleanup is optional. Review the contents before deleting either application-specific Library folder; do not delete `~/Library`, `~/Documents` or your IR library as part of uninstalling the program.

<a id="macos-troubleshooting"></a>
### Troubleshooting

- **Wrong architecture or unsupported OS:** confirm macOS 15+ and choose ARM64 for Apple Silicon or x86_64 for Intel.
- **Only `.cmd` files or Python sources:** you downloaded a Windows or source package. Use one of the Mac application ZIPs above.
- **Blocked or damaged app:** follow the security section; re-download from the release and verify the checksum. Do not treat a malware alert as a normal permission prompt.
- **Export path rejected:** choose a real writable folder rather than a user symlink. Exact Apple system aliases `/var`, `/tmp` and `/etc` are handled, but arbitrary user links remain rejected.
- **Startup or settings problem:** inspect `~/Library/Caches/HYBRID IR/`; back up settings before testing a reset. Report the Mac chip, macOS version, ZIP filename and exact error. Do not attach private IRs or account information to a public issue.

### Mac source code

The matching [macOS preview source ZIP](https://github.com/Leemuzhko/HYBRID-IR/releases/download/v0.4.1/HYBRID-IR-0.4.1-macOS-preview-source.zip) includes `packaging/macos/README.md` and the native build recipe. GitHub's automatic **Source code** archives for `v0.4.1` still represent the original Windows tag, not this Mac snapshot. Native developer builds are documented in the matching source archive; TI compiler-backed development is not included in the Mac application.

[Prepare IRs and banks](workflow.md) · [Technical limits](technical.md)
