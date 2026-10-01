# HYBRID IR for macOS — preview

Native Apple Silicon (`arm64`) and Intel (`x86_64`) applications for **macOS 15 or newer**.
Python, Tcl/Tk and numerical/audio-file dependencies are included. No Homebrew,
Python installation or TI compiler is needed for the Trainer and HIR3A patcher.
This preview is separate from the published Windows release.

## Installation

1. Extract the complete ZIP with Archive Utility; choose the build matching your Mac.
2. Move **HYBRID IR.app** into Applications or your personal Applications folder.
3. Open it, import a WAV, train a FIR/BQ model and export with the HIR3A template.
   Use Zoom Effect Manager to install exported effects; this app does not communicate
   with the pedal directly. TI compiler-backed developer builds are not bundled.

This preview is **ad-hoc signed, not Developer ID signed, and not notarized**.
macOS may block the first launch. After verifying the source and checksum, use
**System Settings > Privacy & Security > Open Anyway** for this application, when
available. Do not disable Gatekeeper globally. If the system reports malware or
the checksum differs, stop rather than bypassing that warning. A Developer ID
signed/notarized general-public release is a separate publication step.

## Files and updates

Preferences: `~/Library/Application Support/HYBRID IR/settings.json`.
Cache and startup log: `~/Library/Caches/HYBRID IR/`.
Default library: `~/Documents/HYBRID IR/Library/`.
No system Python changes and no writes inside the application bundle.
Close the app before replacing it with an update. Uninstall by moving the .app
to Trash; personal projects, IRs, banks and settings remain. Windows installer,
updater and uninstaller scripts are not used. Command-O/S/Q and native opening
of `.irbq` and `.hybridbank` files are provided by the Mac launcher.

Only exact root-owned Apple `/var`, `/tmp` and `/etc` aliases are accepted by
output validation. Arbitrary user links and junctions remain rejected.

## Build from a reviewed public snapshot

Use a native macOS 15+ machine and Python 3.14.6 with Tk. From the public source root:

```sh
python3.14 -m venv /tmp/hybridir-build-venv
/tmp/hybridir-build-venv/bin/python -m pip install --only-binary=:all: -r requirements-zoom-lock.txt -r packaging/macos/requirements-build.txt
/tmp/hybridir-build-venv/bin/python packaging/macos/build_macos.py --source . --out /tmp/hybridir-macos-artifacts --revision COMMIT_SHA
```

Use a new output directory and exact source commit SHA. The builder verifies
`PUBLICATION_MANIFEST.json`, then builds only from that snapshot. It does not
push, tag, publish, or change repository visibility. Source development can use
`python3.14 packaging/macos/launch_macos.py` with runtime dependencies installed.

`MACOS_BUILD.json` records source identity and dependency versions. `VALIDATION.json`
records the relocated actual .app, direct and LaunchServices startup, native Tk,
training, WAV/project/bank round trips, raw macOS temporary-path export, K-weighted
modes and defaults across a fresh process. Host checks are not an audible playback
or pedal compatibility claim. A/B rendering is checked; listening and prolonged
hands-on use need testing on a physical Mac.

Apple guidance: https://support.apple.com/en-us/102445
PyInstaller: https://pyinstaller.org/en/stable/feature-notes.html
