# ADR 0014: trained RESO, free Presence correction, runtime RBJ controls

Date: 2026-09-27. Status: accepted for local candidate; pedal gate open.
Supersedes the control/table semantics of ADR 0013, not its byte/identity gates.

## Context and invariant

Trainer's Resonance is a fitted Peak which can already compensate cabinet
resonance. Prefixing a new default RESO made it static and counted two extra
sections. RESO must retain that Peak's frequency, Q and nominal gain; displayed
0.0 is a gain delta relative to the fitted baseline, not necessarily zero gain.
Arbitrary SOS/name/position inference is prohibited. OFF has no cabinet data:
standard RESO 110 Hz, Q .7, nominal gain0 and common PRES3500 Hz, S .8.

## Decision

- New presets tag only `Biquad.control_role='reso'`. Presence is an unlocked
  ordinary HighShelf correction. Common PRES is an independent neutral shelf.
  Thus tagged `128+8` exports as9 BQ; untagged8 sections export as10 until the
  user confirms legacy Resonance ownership. Generic FIR-only exports2 controls.
- Persist roles in Model/Bank/Trainer packages. Old explicit `pres` metadata
  from the unreleased prototype upgrades to unlocked correction without changing
  coefficients. Unmarked legacy filter locks are not silently altered. Duplicate
  filters and changing filter kind clear ownership; invalid roles fail closed.
- HVB4 replaces coefficient tables with12 bytes RESO parameters per descriptor
  (inside its existing48 bytes),12 shared PRES parameters and a244-byte gain LUT.
  RESO/PRES calculate5 float32 coefficients when their smoothed position changes,
  once per callback/active branch, not per audio sample. No table in state RAM.
  C674 reciprocal/rsqrt use two Newton refinements; host reciprocal/sqrt are
  numerical references, not proof of intrinsic or whole-pedal parity.
- Preserve imported RESO coefficients exactly at nominal delta0; common PRES
  is exactly identity at0. Other correction SOS and FIR scale/gain remain exact.
  Cascade reordering preserves the neutral transfer function, not bitwise audio.
  Host validates RBJ ramp samples and Jury margins. Runtime checks every derived
  denominator and falls back to nominal RESO / identity PRES if unsafe.
- Serial switching: old routing/IR runs during64-sample fade-out; commit/reset
  at zero gain, then128-sample fade-in. Latest requests during fade-out coalesce;
  requests during fade-in defer. Fade affects both outputs. No double convolution.
  Inactive selector changes do not interrupt audio. FIR history stays float32.
- Pinned HVB4RBJ template, conservative code+const28904B and fardata144B; service
  sizes cannot grow relative to that template. This is inherited engineering
  policy, not a newly established hardware limit. Old ZDLs/banks are not replaced.

## Alternatives and consequences

HVB3 per-model tables were prototyped but not sent to the pedal. They preserve
curves but add1220 bytes for each distinct control curve, making8-slot banks
unnecessarily expensive. Init-generated tables would add RAM and startup work.
Direct RBJ avoids both, at the cost of bounded control-update arithmetic. Overall
loading capacity still depends on compiled code size, not only coefficient bytes.
Two-stage crossfade rejected for this candidate because it needs duplicate FIR.

## Validation and unresolved risk

Owner: [HVB4 candidate](../HIR3A_RELEASE_NOTES.md). Targeted Python/native
C/GUI tests and TI smoke are required; their commands/results live there.
HBUNIT, HB9BQ and HB8RBJ received a user-reported functional PASS on MS-70CDR
on 2026-09-27; the owner records exact hashes and scope. Sustained control-ramp
CPU cost, detailed switching quality and amplifier-chain headroom remain open.
