# ADR 0015: portable authoring projects and processed IR library

Date: 2026-09-27. Status: implemented in Trainer 0.4.0.

## Decision

Keep the existing Trainer, generic numerical fitting and pinned HVB4RBJ export.
The authoring layer adds no DSP code, coefficient changes or hardware claims.

- `authoring.py` owns portable interchange; `library_panel.py` owns selection
  and library actions; `zoom_panel.py` owns bank edits and stable slot identity;
  `WorkspaceMixin` owns installation of a Session and unsaved-project prompts.
- `.irbq` schema `irbq-project/2` contains model, preparation settings, snapshots,
  log and available source/target/pre-MPT arrays. The reader also accepts v1.
  Older apps may not understand v2. Missing references remain missing: model-only
  editing and saving are allowed, but training/comparison/audio require a real
  target. Attaching a user-selected WAV prepares a real target and retains the
  fitted model; it does not silently use model output as training truth.
- `.hybridbank` schema `hybrid-ir-bank/1` is a ZIP with `bank.json`, embedded
  128x64 PNG and one `.irbq` Session per slot. No local stock/output/library
  paths are stored. The card is materialized in a content-addressed profile
  cache. Portable metadata is whitelisted; unexpected keys/local folder paths
  are rejected before loading Sessions or touching that cache. Library scans
  reject invalid Zoom role/control counts and report them as unreadable entries.
  UIDs identify slots across reordering; opening another bank clears
  the editing binding. Update applies a cloned Session to that UID, not row index.
- Legacy `.zoombank.json` remains readable/writable and models-only. Saving
  this format with retained Sessions asks for consent to loss of references.
  A new empty bank can be saved; an empty bank cannot export to ZDL.
- Library defaults to `Documents/HYBRID IR/Library`, is user-selectable and
  separate from shipped/publication data. It reads `.irbq` and `model.json`;
  imported JSON becomes a model-only `.irbq`. Search/type/max FIR/max BQ filters
  and multi-selection do not modify models. Batch bank insertion validates all
  selected models/role choices before mutation. Automatic labels use at most
  five ASCII characters; existing manual label rules stay unchanged.
- Save/Discard/Cancel and explicit library overwrite prompts protect edits.
  New/Open bank prompts for dirty Trainer edits bound to a slot before clearing
  that binding. Discard restores the bank's stored Session; if subsequent bank
  navigation is cancelled, that restored Session keeps its original binding.
  All Save-as paths have an application-owned overwrite prompt,
  independent of native dialog behaviour; ordinary Save reuses the known path.
  Existing file save reuses its path; Save as chooses another path. Recent
  project/bank paths and library folder are local preferences, not portable data.
- Archive caps: 64 MB file, 64 ZIP members, 256 MB expanded outer bank;
  128 MB float64 signal data per project/bank. NPY shape/dtype/payload are
  checked before allocation; pickle is prohibited; entry names are fixed, no
  archive extraction. Library scan caps 1000 projects/10000 filesystem entries
  and 256 MB retained reference data. Unreadable files are reported, not used.

## Interface

Bank/library views start at approximately 50/50 graph/table height. A draggable
divider remains; revisiting the same view does not keep resetting user position.
The graph is not flattened or hidden. Compact authoring controls reuse theme
tokens; file operations are grouped in menus. Bank budget/slot indicators are
right below output-folder fields. Right settings scroll on the minimum window;
the table retains its own scrollbar. Indicators show storage/slots, not DSP %.

## Validation and limits

Exact Session arrays/models/snapshots and HVB4 packed bytes are round-trip gates.
GUI checks cover filters, transactional insertion, clone isolation, UID update
after reorder, cancellation, persistence, theme rebuild and actual layout at
1440x930 / 1100x740. Screenshots use synthetic models only. Tests do not establish
new pedal parity; the pinned runtime/template and previous hardware evidence
remain unchanged. Library import validates its full selection first, but separate
file writes are not a multi-file filesystem transaction.

Owner: [current tool](../../README.md). User workflow:
[English](../en/workflow.md), [Russian](../ru/workflow.md),
[Ukrainian](../uk/workflow.md).
