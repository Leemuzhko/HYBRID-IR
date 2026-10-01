# macOS 13 / 12 compatibility candidate

[Русский](README.ru.md)

**Development-only additional package.** Primary target: macOS 13 Ventura;
secondary target: macOS 12 Monterey. The declared binary floor is 12.3 for both
Apple Silicon and Intel. A passing build/header audit on macOS 15 is **not proof
of operation on macOS 12 or 13**. Validate these exact ZIPs on the target systems
before publishing them or advertising additional supported OS versions.
Existing macOS 15+ and Windows release packages are not replaced.

## Packaging contract

The first complete ARM64 bundle audit rejected a 12.0 target: the selected SciPy
wheel is named `macosx_12_0` but its Mach-O modules and Fortran libraries declare
**12.3**. The shared compatibility profile therefore explicitly requires **12.3+**
on both architectures; 12.0–12.2 are not claimed. The strict audit is unchanged.

Python/application/DSP versions are unchanged. NumPy 2.5.3 and SciPy 1.18.1 offer
multiple macOS wheels; ordinary installation on a new OS prefers 14.0 variants.
The two compatibility requirements files lock every runtime/build dependency to
an exact lower-target wheel URL and SHA-256. No binary header is patched to
conceal a higher requirement. Trainer and HIR3A patching need no TI compiler.

`../build_macos.py --profile compat12` builds the extra package. Default profile
`standard` retains minimum 15.0 and its archive naming. `../audit_macho.py` checks
the selected slice of every Mach-O, deployment commands, Info.plist, bundle links
and non-system absolute dylib paths. Failed gates stop packaging, not silently
raise the minimum. The scan is not complete symbol/API-availability analysis.

ZIP names are `HYBRID-IR-<version>-macOS-arm64-compat12-preview.zip` and
`HYBRID-IR-<version>-macOS-x86_64-compat12-preview.zip`. Each contains
`HYBRID IR.app`, EN/RU instructions and build/deployment metadata. The compatibility
bundle has a different identifier, but uses the same HYBRID IR preferences path:
back up your data and do not run both app variants concurrently.

## Build from the generated public mirror

Use a native Mac and **CPython 3.14.6 with Tk**, in a clean venv. Do not subsequently
install general requirements, which can replace wheels with newer-platform variants.
From the development repository root, after committing sources and regenerating
the mirror as documented in `HYBRID-IR/publication/README.md`:

```sh
SOURCE="$PWD/HYBRID-IR/publication/repo"
REVISION=$(git rev-parse HEAD)
WORK=$(mktemp -d /tmp/hybridir-compat.XXXXXX)
ARCH=$(uname -m)
python3.14 -m venv "$WORK/venv"
"$WORK/venv/bin/python" -m pip install --force-reinstall --require-hashes --only-binary=:all: -r "$SOURCE/packaging/macos/compat/requirements-$ARCH.txt"
"$WORK/venv/bin/python" -m pip check
"$WORK/venv/bin/python" -B "$SOURCE/scripts/run_development_tests.py"
"$WORK/venv/bin/python" -B "$SOURCE/packaging/macos/build_macos.py" --source "$SOURCE" --out "$WORK/packages" --revision "$REVISION" --profile compat12
```

The builder verifies installed `direct_url.json` wheel identities and source hashes,
checks the actual resulting binaries (including Python, Tcl/Tk, OpenBLAS/Fortran
and the PyInstaller bootloader), then verifies the ad-hoc signature and tests the
relocated read-only `.app` directly and through LaunchServices.
`MACOS_BUILD.json` records the real host OS. `MACOS_DEPLOYMENT.json` is static
evidence; `VALIDATION.json` is host runtime evidence. CI uploads ZIPs only after
successful checks. `../tests/test_compat.py` contains portable packaging regressions.

## Install and validate on the target OS

Choose the correct architecture, verify the adjacent `.zip.sha256` using
`shasum -a 256 -c <file>.zip.sha256`, then extract with Archive Utility. Keep the
`.app` intact in a separate test folder. Python/Homebrew is not needed on the
target Mac. Back up preferences, projects, banks and original audio first.

This is **ad-hoc signed, not Developer ID signed or Apple-notarized**. For a verified,
trusted package, use Apple's application-specific Open Anyway route when offered.
Do not globally disable Gatekeeper or bypass malware, damage or checksum warnings.
A signature or matching ZIP checksum is not a malware guarantee.

Test on a real macOS 13 machine first, then 12.3 or newer Monterey. Record OS version, architecture,
ZIP SHA-256, Finder launch, WAV import, FIR + BQ fitting (not FIR-only), all
K-weighted modes, defaults after restart, project/bank roundtrips, A/B listening,
and HIR3A export to an ordinary writable directory. A synthetic diagnostic is:

```sh
WORK=$(mktemp -d /tmp/hybridir-target-test.XXXXXX)
"/path/to/HYBRID IR.app/Contents/MacOS/HYBRID IR" --self-test "$WORK"
```

Keep `report.json` and startup logs. Separately record Finder/quarantine behavior;
command-line launch is not the same test. Physical pedal installation and listening
remain separate gates. Do not expand the supported-OS list solely from load commands
or a successful test on macOS 15.

Settings: `~/Library/Application Support/HYBRID IR/settings.json`; cache/logs:
`~/Library/Caches/HYBRID IR/`; library: `~/Documents/HYBRID IR/Library/`.
Replacing/removing the whole `.app` leaves these files intact. Keep originals and
backups when changing versions.

## Provenance and limitations

Wheels were resolved for `macosx_12_0` / `cp314` and checked against PyPI hashes on
2026-09-30. Dependency notices are retained by the existing packaging recipe.
Building on the oldest supported OS is preferable; this CI uses macOS 15 and does
not establish runtime support on 12/13 or Apple security approval.

[NumPy files](https://pypi.org/project/numpy/2.5.3/) ·
[SciPy files](https://pypi.org/project/scipy/1.18.1/) ·
[PyInstaller compatibility](https://pyinstaller.org/en/stable/usage.html#macos) ·
[Apple security guidance](https://support.apple.com/en-us/102445)
