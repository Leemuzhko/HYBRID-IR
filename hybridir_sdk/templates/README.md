# Template files

The application ships only **HIR3A.ZDL** and **HIR3A.template.json**.
The original HIR3A bytes have user-reported pedal acceptance. New exports need
independent pedal checks; a passport and a byte budget do not measure DSP load.

HYBRID4, HVB4RBJ and HVB4REF are synthetic, source-only regression fixtures.
The optimized HVB4RBJ hash a6525065 is a known slot-insertion failure, not a
fallback. These legacy files are explicitly excluded by the application packager.
Keep the source-only fixtures for regression tests; do not install them as releases.
All template binaries contain inherited runtime material: see THIRD_PARTY_NOTICES.md.
