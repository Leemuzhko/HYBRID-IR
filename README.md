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
<h3 align="center"><a href="https://github.com/Leemuzhko/HYBRID-IR/releases">Download for Windows</a></h3>

**[Standalone — recommended](https://github.com/Leemuzhko/HYBRID-IR/releases)** · **[Lite — Python required](https://github.com/Leemuzhko/HYBRID-IR/releases)**

Choose the matching ZIP under release Assets. Both include the same app for their revision; development builds are prereleases. GitHub Download ZIP contains source code, not the installed app.

<p align="center"><a href="docs/en/installation.md">Installation</a> · <a href="docs/en/workflow.md">Build your first effect</a> · <a href="https://ko-fi.com/leemuzhko">Support on Ko-fi</a></p>
<p align="center">MS-50G · MS-60B · MS-70CDR · G1on · G1Xon · B1on<br>
<sub>Project device family. Hardware validation varies by model and bank; see the technical guide.</sub></p>

---

I built HYBRID IR to use my own cabinet responses on Zoom pedals. You can load a conventional IR or fit a shorter FIR with supporting IIR filters, then package your sounds into a selectable ZDL bank. The tools are free; the standard patcher needs no TI compiler.

## Documentation

Looking for something ready to try? My [Zoom-ZDL-FX repository](https://github.com/Leemuzhko/Zoom-ZDL-FX/tree/main/zdl/) contains ready-made ZDL effects. Check each effect's notes and compatibility before installing it. HYBRID IR is the tool for preparing your own banks.

- [Installation, updates and removal](docs/en/installation.md)
- [Prepare IRs and build a bank](docs/en/workflow.md)
- [Limits and technical details](docs/en/technical.md)

<a id="installation"></a>
<a id="workflow"></a>

## Quick start

Install the desktop app, open **Zoom ZDL**, add an IR with **Import WAV**, and export with **Patch ZDL (no TI)**. Transfer the resulting ZDL with [Zoom Effect Manager](https://zoomeffectmanager.com/en/download/). The guides above cover the settings and checks.

## What's new in 0.4.1

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
characters for slot labels. See the [technical guide](docs/en/technical.md).

DSP cost **20** is not CPU usage. Two long IRs plus an amplifier may overload
the pedal. Use a shorter IR or L/R mode and check the whole chain by ear.
IR OFF does not shut down all branch processing. This is cabinet filtering,
not an amplifier or distortion model.

## Support the project

If HYBRID IR is useful to you, you can [support my work on Ko-fi](https://ko-fi.com/leemuzhko). It helps me develop, test and document the project. The tools remain free; a donation does not buy features, priority support or a release deadline.

[Source code and third-party notices](docs/en/technical.md) · [MIT](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)
