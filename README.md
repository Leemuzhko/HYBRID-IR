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

Install the desktop app, open **Zoom ZDL**, add an IR with **Import WAV**, and export with **Patch ZDL (no TI)**. Transfer the resulting ZDL with [Zoom Effect Manager](https://zoomeffectmanager.com/en/download/). The guides below cover the settings and checks.

## Before you start

The bundled HYBRID4 template holds **up to 4 IRs + OFF**, at most **2048 samples per IR**, with a **shared 4096-sample FIR pool**. It cannot hold four different 2048-sample IRs. Keep slot names to **5 characters** for the pedal display.

DSP cost is deliberately low and fixed at **20**, not a CPU percentage. Listen to the complete chain: if it crackles, use a shorter IR or **L/R** mode to run one branch. IR **OFF** alone is not a complete branch shutdown. See the technical guide before testing.

My documented prototype tests used an **MS-70CDR, firmware 2.10**. They do not validate every listed model, new bank or the bundled experimental template. This is cabinet filtering, not an amplifier or distortion model.

## Support the project

If HYBRID IR is useful to you, you can [support my work on Ko-fi](https://ko-fi.com/leemuzhko). It helps me develop, test and document the project. The tools remain free; a donation does not buy features, priority support or a release deadline.

[Source code and third-party notices](docs/en/technical.md) · [MIT](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)
