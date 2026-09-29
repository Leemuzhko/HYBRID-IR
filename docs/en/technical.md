# Limits and technical details

[English](../en/technical.md) · [Русский](../ru/technical.md) · [Українська](../uk/technical.md)


**HIR3A is selected automatically for Patch ZDL (no TI).** Its original synthetic
template has user-reported MS-70CDR operation, parameter persistence and patched
export acceptance. New banks still need their own pedal checks. The application
packages contain only HIR3A and its hash-paired template passport.

**K-weighted normalization** is available alone, with the 80–8000 Hz band,
with Pink weighting, or with both Pink and that band. This is frequency-weighted
IR response normalization, not a gated LUFS meter. Existing normalization modes
remain available; export does not secretly renormalize the saved model.

Use **Save as default** in Preparation to retain the current preparation settings,
including normalization. **Load defaults** restores them; the next application
start restores them automatically. These are preparation defaults, not named
profiles or a saved set of training-optimizer parameters.

The library and portable projects/banks retain original audio for explicit
re-preparation. Older model-only projects remain usable. Keep backups: older
program versions may not read the new original-audio schemas.

The template allows **1–8 IR slots + OFF**, FIR **32–4096 taps** and at most
**32 BQ per entry**, including RESO/PRES. The total byte budget takes priority:
code is 16,800 B; constants may use 12,104 B, including a 1,672 B prefix.
Two independent 4096-tap IRs do **not** fit this profile. Use at most 5 visible
characters for slot labels. See the [technical guide](workflow.md).

DSP cost **20** is not CPU usage. Two long IRs plus an amplifier may overload
the pedal. Use a shorter IR or L/R mode and check the whole chain by ear.
IR OFF does not shut down all branch processing. This is cabinet filtering,
not an amplifier or distortion model.


## HIR3A template

| Field | Value |
| --- | ---: |
| `.text` | 16,800 B |
| `.const` budget | 12,104 B |
| Constant prefix | 1,672 B |
| Bank budget (including bank metadata) | 10,432 B |
| Code + constants cap | 28,904 B |
| `.fardata` | 144 B |
| Card image | 128×64 monochrome, at most 848 RLE bytes |
| Zoom Effect Manager icon | 128×96 RGBA |

The passport pins the exact original ZDL SHA256:
`14f605e66ea0ca24a1bd0b0873cb15b8dbaf900290ffe78f9f6cb60c99b0f9d4`.
These are conservative, template-specific storage limits, not universal hardware
limits or measurements of processing time. The normal patcher uses a prebuilt
binary, so no TI compiler is required. Firmware version and installed-file hash
were not independently read back in the HIR3A user test.

The active SDK linker includes a bounded cross-section SHT_REL/PCR_S21 fix.
That fix does not establish correctness for all C6000 relocations. HIR3A keeps
private T7 edit-handler tails; rejected shared compact handlers are not adopted.

Changing a bank, model name, effect ID or card image does not rebuild DSP code.
New passport/ID validation and output transactions remain active. Import only
trusted template packages; SHA256 proves pairing, not authenticity or safety.
The supplied UNIT bank is synthetic, not a commercial cabinet IR.

## Source and licensing

Project code is MIT; inherited Zoom runtime material and user-loaded IRs are not
relicensed by that declaration. The template is not clean-room/MIT-only.
Keep [third-party notices](../../THIRD_PARTY_NOTICES.md), `licenses/` and the
provenance files with distributions. The source-only synthetic legacy templates
are regression fixtures and are not included in Lite/Standalone packages.

Run `python -B scripts/run_development_tests.py` from the source root for host
checks (Tk/desktop required for GUI tests). Windows lifecycle tests must run on
Windows. Optional TI/private-fixture tests are listed separately, not counted as
passing. Source manifests and archive hashes check integrity, not authenticity.
