# Prepare IRs and build a bank

Release 0.4.1: HIR3A is the default template passport for
**Patch ZDL (no TI)**. No manual template selection is needed. Its code uses
16,800 bytes; the conservative code + constants budget is 28,904 bytes.
New banks still need a pedal check. Other passports remain selectable.

**English** · [Русский](../ru/workflow.md) · [Українська](../uk/workflow.md)

[Home](../../README.md) · [Installation, updates and removal](installation.md) · [Limits and technical details](technical.md)

Start with a plain FIR if that is what you need. Hybrid fitting is an option for balancing sound and DSP load, not a mandatory conversion step.

## What is HYBRID IR, and why use it?

A cabinet impulse response (IR) describes how a cabinet/microphone setup
filters a signal. A conventional IR loader reproduces that response using
convolution with the stored samples. Longer direct FIR filters require more
work per audio sample, which matters on a pedal with a limited DSP budget.

HYBRID IR combines a **FIR filter** with a **chain of biquad (IIR) filters**.
The idea is to let efficient biquads reproduce part of the cabinet's response,
leaving a shorter FIR to handle the remaining detail. This can offer a useful
accuracy/CPU trade-off instead of spending the whole budget on a long FIR.
Savings depend on FIR length, biquad count and the other effects in the chain;
there is no universal performance or sound-equivalence guarantee.

The desktop **IRBQ Trainer** fits this model to your WAV, lets you compare
responses and audition the result, and exports the prepared model. “Training”
here means numerical filter fitting on the computer, not a neural network
running in the pedal. The **ZDL Patcher** packages your selected models into
one effect with selectable slots. The pedal runs the prepared filters and
provides routing, output level, presence and resonance controls.

This is useful when you want your own cabinet sounds alongside an amp effect
on a resource-limited MultiStomp. A fitted hybrid model is an **approximation**:
matching a magnitude response does not alone establish identical phase,
transients or sound. Compare and listen before exporting, then test the pedal
chain. This is cabinet filtering, not an amp/distortion model or a claim that
all long IRs can be replaced transparently. Importing a WAV directly into a
bank does not automatically perform hybrid fitting; prepare it in Trainer first
when you want that trade-off.

## What the patcher does

Trainer fits your cabinet response; the integrated **Zoom ZDL** tab assembles
the resulting models into a HYBRID IR effect. **Patch ZDL (no TI)** writes the
bank and supported metadata into the bundled, verified template without
recompiling DSP code. You do not need the TI compiler or stock donor files.

You can select the bank contents, rename slots and the effect, choose its ID,
and supply a compatible card bitmap. The patcher validates template identity
and capacity before writing a `.zdl` and a `.patch.json` report. It does not
modify arbitrary ZDL effects or upload anything to the pedal.

## Plain FIR or FIR + correction BQ?

Extra correction biquads are optional. To use a cabinet IR as ordinary convolution,
use **Zoom ZDL → Import WAV**, choose the FIR length and export the bank without
training correction BQ. Import uses the current preparation settings at 44.1 kHz,
then truncates or zero-pads to the chosen length; the packer converts coefficients
to Q15 with the required scale. Check those preparation settings: this is not
necessarily a byte-for-byte copy of the WAV.

A sufficiently long FIR can retain the desired cabinet response without extra
correction BQ. Length alone is not a guarantee: truncation can change the response,
so compare the result. FIR + BQ fitting is an alternative when you want a shorter
FIR supplemented by filters, not a required step for every IR.

**HVB4RBJ reuses trained RESO.** New Trainer presets explicitly
tag Resonance as RESO. Its fitted frequency, Q and baseline gain remain; 0.0 on
the pedal means zero adjustment relative to that baseline. Presence is now
unlocked and trained as ordinary correction. A separate common PRES is added,
so **128+8 gives 9 BQ**, not10.
For an older unmarked model, the editor asks whether to reuse Resonance. No
arbitrary SOS is guessed. Generic `K` correction filters give `K+2`; with no
correction, **BQ total = 2**. A tagged model gives `K+1`, with at most32 total.
These filters do not shorten the FIR. The legacy fixed patcher retains its old
semantics and rejects tagged models: use Patch ZDL. The RBJ smoke banks passed
user-reported functional tests on MS-70CDR; exact behaviour and DSP headroom in
each effect chain still need checking.

## Everyday workflow

### Projects, library and corrections

Trainer 0.4.0 adds **Library**. Its default folder is
`Documents/HYBRID IR/Library`; choose another folder if you prefer. Save a
prepared model with **Save current to library**, or import `.irbq` projects/model
JSON using **Import**. Search and type/max FIR/max BQ filters narrow the table.
Select several rows and use **Add selected to bank**. Nothing is added if a
role confirmation is cancelled; generated labels fit within five ASCII characters.

In **Zoom ZDL**, **New bank** starts an empty bank. **Bank** holds Open, Save as,
recent banks and Size estimate. **Save bank** writes to the existing path.
The default `.hybridbank` file embeds each model's available source/reference,
settings, snapshots and the card PNG, so you can move it without collecting
separate files. Legacy JSON stores models only and asks before dropping references.
Keep your own IR library/projects outside the application install folder.

Double-click a bank slot or choose **Edit in Trainer**, adjust it, then return
and click **Update slot**. The update follows that slot even if rows were moved.
The bank is unchanged until you apply the update. A legacy slot without its WAV
opens as model-only: manual editing and `.irbq` saving work, but training and
reference comparison do not. Use **File → Attach reference WAV** to supply a
real target without replacing the fitted model. A ZDL alone cannot reconstruct
the original training project.

**Open project / Save project**, Save as and recent projects are available in
File. Unsaved changes offer Save/Discard/Cancel. The authoring v2 `.irbq` reader
accepts old v1 projects; an older Trainer may not open new v2 files. Archive and
library scan limits are documented in [ADR 0015](../adr/0015-portable-authoring-library.md).
The graph and bank/library start at roughly half the height each; drag the
divider as needed. Budget indicators are compact and right-aligned. They are
storage/slot limits, not a DSP load meter. Use the [update procedure](installation.md)
to replace an older installed version.

1. For a plain FIR, use **Zoom ZDL → Import WAV** as described above. For a hybrid
   model, load the WAV in Trainer and fit the response, or open a prepared model.
2. Open **Zoom ZDL**. A WAV imported there is already in the bank. For a trained
   model, use **Current model** or import Trainer JSON exports;
   arrange the bank and set the slot labels, effect name and ID.
   Keep slot labels to **5 ASCII characters or fewer**: longer names can extend
   beyond the pedal's display field, as observed on hardware. The file format
   accepts up to 7; that is a storage limit, not a display-fit guarantee.
3. Select **Zoom Effect Manager custom folder:**: the same folder you configured in Zoom
   Effect Manager to read custom effects. Exports are saved directly into this folder.
   Bundled reserved IDs are always checked; no stock ZDL folder is needed.
   Resolve any
   conflict before exporting, then save the bank project for later editing.
4. Click **Patch ZDL (no TI)**. A confirmation shows the saved ZDL path after export.
   Existing files require overwrite confirmation. **Build ZDL** is the
   optional developer compiler path, not the button needed for normal use.
5. Keep the generated effect subfolder intact. Install the
   effect using **Zoom Effect Manager**, as described below, then test it on the pedal.
   The app does not flash devices.

### Export folder

**Patch ZDL (no TI)** creates a subfolder named after the ZDL basename:

```text
Selected output folder/
  MYCAB/
    MYCAB.zdl
    MYCAB.json
    MYCAB.png
    MYCAB.patch.json
```

`MYCAB.json` is Zoom Effect Manager metadata: effect name, device filename,
icon filename and English/Russian descriptions. `MYCAB.png` copies the selected
card image without changing its polarity. `.patch.json` is a separate technical
report, not manager metadata. Keep all four files together. Existing files
require confirmation before replacement; unrelated files are preserved.
Choose an ordinary output path without symbolic links or Windows junctions.
For old flat exports, move the previous ZDL outside the scanned folder before
exporting again, so the recursive scan does not find two copies.

Enable ZDL folder reading in Zoom Effect Manager, select the parent folder,
then restart it after exporting or updating files. See the official
[folder format and settings](https://zoomeffectmanager.com/en/posts/reading-effects-from-folder/).
The optional developer **Build ZDL** path still uses its existing flat export.

## Install the ZDL on the pedal — Zoom Effect Manager required

Use [Zoom Effect Manager (download)](https://zoomeffectmanager.com/en/download/)
to install the generated HYBRID IR `.zdl` on the pedal. This is the required
transfer tool for the workflow documented here, not an optional part of Trainer.
Trainer/Patcher only creates the file; its installer installs the desktop app,
not the effect on the pedal. Zoom Effect Manager is a separate third-party tool.

Use version **2.3.3 or newer** for reading custom ZDL files from a folder;
the project's release notes introduce that feature in 2.3.3. Put your generated
ZDL in a dedicated folder and use the manager's folder-loading feature, then
follow its instructions for your pedal model to write the effect. Connect the
pedal before starting the manager and restart it after writing, as its download
page instructs. Back up your presets first and do not disconnect USB or power
during writing. Installing a file does not establish its DSP/RAM safety.

English/dark is the default; language and theme controls are in the toolbar.

The custom folder is scanned recursively by ZDL header identity (GID + FXID),
not filename. This folder is also the export destination; it is only requested
if the field is empty. Portable banks omit local paths and use the current folder.
Reserved identities cannot be replaced, even with a matching name. Custom
same-name/ID replacements require confirmation; conflicting names get a free-ID
suggestion. The bundled catalog is a collection snapshot, not a live inventory
of the pedal or a guarantee against future IDs.
It reserves 255 identities from 450 Zoom Effect Manager original-effect files, including the
bundled Other effects RainSel, RTFM and Div0 (stored under Filter in that collection).
Source filenames and SHA-256 hashes are retained in `irbq_lab/irbq/stock_ids.json`;
no donor ZDL files are bundled with the catalog.

---

[Home](../../README.md) · [Installation, updates and removal](installation.md) · [Limits and technical details](technical.md)
