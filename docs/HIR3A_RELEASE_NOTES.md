# HYBRID IR 0.4.1

Default compiler-free HIR3A template, K-weighted normalization and saved preparation defaults.

## Changes

- The patcher now selects the hash-paired HIR3A passport at startup.
- Lite and Standalone contain the same application; only HIR3A is shipped as the runtime template.
- K-weighted, K + band, K + Pink and K + Pink + band normalization remain available.
- Preparation defaults can be saved, loaded and restored on restart. Failed saves no longer report success.
- Opening an empty authoring bank works; exporting one is still rejected before output.
- Zoom WAV import uses current preparation settings, including restored defaults.
- Portable banks retain original audio without silently changing saved fitted models.
- Publication includes all passport/preparation modules and installer helpers.
- Packaging supports both a standalone repository and the HYBRID-IR monorepo subdirectory.

## Downloads and installation

Use **Standalone** for an offline install without system Python.
**Lite** requires official Windows x64 Python 3.14 with Tk and downloads dependencies.
Extract the whole ZIP and run `Install_HYBRIDIR.cmd`. For updates close the app,
use the same flavor/channel, and retain backups. These are ZIP setup packages,
not signed EXE/MSI installers. See `docs/en/installation.md` (RU/UK also included).

## Hardware scope

The original HIR3A SHA256 is
`14f605e66ea0ca24a1bd0b0873cb15b8dbaf900290ffe78f9f6cb60c99b0f9d4`.
User-reported MS-70CDR checks covered operation, parameter persistence and patched
exports. New banks and chains require checking; host tests do not measure C674
processing time. Two long IRs with an amplifier can overload DSP. The 28,904-byte
code+const gate is template-specific, not a general pedal limit.

## Support and licenses

Support development: https://ko-fi.com/leemuzhko

Project code is MIT. Keep THIRD_PARTY_NOTICES.md and included licenses.
Stock-derived runtime material and user IRs retain their separate rights.
