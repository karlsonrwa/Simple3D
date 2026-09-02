# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, read_step, volume, entity_count

"""The C++ baseline: the port must reproduce the original exporter's board.

12073.309477 mm3 is what the C++ tool this port replaced wrote for
demo/ap-214 with the soldermask thicknesses zeroed, which is how it was
measured; the volume is compared to 1e-4 mm3.

The entity count is a property of the WRITER, not of the geometry, and it has
moved twice with the volume unchanged: 5077 at the first Python rewrite
(1c5d46b), 5054 from 3ad1617 (the number round 21 recorded) through a402fff,
5038 since 687ea3f (round 63: an arc is read by its two ends). It is pinned so
that the next move is noticed, not because the number is sacred - a deliberate
writer change moves it, the volume still has to match, and the new count is
recorded here with the commit that moved it.

Until round 70 this script printed MATCH or DRIFT and exited 0 either way.
"""
import json, sys
from stepbuilder import core

BASELINE_VOLUME = 12073.309477
BASELINE_ENTITIES = 5038

out = out_dir("regression")
d = json.loads((ROOT / "demo/ap-214/demo.json").read_text(encoding="utf-8"))
d["pcb"]["thickness"]["soldermask_top"] = 0.0
d["pcb"]["thickness"]["soldermask_bottom"] = 0.0
jf = out / "nomask.json"
jf.write_text(json.dumps(d))
core.generate(step_dir=ROOT / "demo/step_files", json_file=jf, output_dir=out,
              output_name="nomask", minimize_size=False, log=lambda m: None)

step = out / "nomask.step"
v = volume(read_step(step))
n = entity_count(step)
print(f"volume (masks zeroed) = {v:.6f}   entities = {n}")
check(f"volume matches the C++ baseline {BASELINE_VOLUME}",
      abs(v - BASELINE_VOLUME) < 1e-4, f"drift {v - BASELINE_VOLUME:+.6f}")
check(f"STEP entity count is {BASELINE_ENTITIES}", n == BASELINE_ENTITIES, f"got {n}")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
