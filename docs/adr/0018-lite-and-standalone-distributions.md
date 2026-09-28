# ADR 0018: Separate Lite and Standalone application downloads

Status: implementation candidate, Windows lifecycle/release gates required.

## Context and invariant

GitHub source archives are not application releases. Users need either a small
download using their installed Python or a self-contained offline installation.
Both flavors must use exactly the same application and ZDL bytes for one source
revision. Packaging does not establish new hardware acceptance.

## Decision

Build from an immutable revision of each bounded public/development repository.
Export application, templates, runtime helpers, user guides and licenses, not
tests, research documents, private banks, or the parent checkout. Lite retains
the receipt-based installer and private venv. Standalone bundles Windows x64
CPython 3.14 with Tcl/Tk and freshly resolved locked wheels; never relocate an
existing venv. Explicit `python314._pth` ignores machine Python paths. Both use
the same installer and updater, with no pip/network step for Standalone.

Standalone ships as an extracted ZIP with `Install_HYBRIDIR.cmd`, not a signed
single-file EXE or MSI. This avoids introducing a second installer lifecycle.
No system Python, registry Python installation, or global PATH change is needed.
Uninstall stages only the Python/Tk runtime and uninstall helpers outside the
installation; the temporary supervisor cleans its own staging directory after
the interpreter exits. Application deletion still follows the existing receipt.

Stable/development have separate default installation, desktop shortcut and
preferences paths. Updates reject cross-channel and cross-flavor replacement;
install side by side to change flavor. Existing Lite installations without
delivery metadata are treated as stable Lite. Personal files and backups retain
the existing ADR 0012 protections. Shared libraries are user-selected, not erased.

## Alternatives and consequences

PyInstaller freezing was considered but would introduce frozen-resource paths
and another launcher/uninstaller lifecycle. A bundled explicit interpreter keeps
the current Python module/template paths intact. It makes the full download
larger and does not hide source code. Runtime licenses and per-file hashes ship
with the package; hashes are integrity checks, not code signing.

Windows Actions builds both artifacts from one commit, with checksums. Release
publication must be explicit; development is always a prerelease. Updating a
README link must not imply that an unbuilt asset exists.

## Validation and remaining risks

`tests.test_distribution`, installer/update/uninstall suites cover offline branch,
manifest integrity, legacy behavior, identity gates and user-file preservation.
Actual Windows install, moved-runtime imports/GUI, update and external uninstall
must be checked separately. A PATH-isolated smoke is not a pristine Windows VM.
Runtime files are generated build dependencies, not committed binaries.
