# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, read_step, count_solids

"""End-to-end: a JSON whose component keys are synthetic mechanical names
(CR2032_MECH1 / _MECH2, no refdes) must build, place under symbols_top and
symbols_bot, and share one part between the two identical models."""
import json, sys

# The PACKAGE import, not a bare `core`: core.py reaches sideways to its
# siblings (`from .colors import ...`, `from .bend import ...`) inside the
# functions that need them, and a bare module has no package to reach from.
# The failure is an ImportError deep in generate(), on whichever feature the
# test happens to exercise.
from stepbuilder import core

demo = json.load(open(ROOT / "demo/ap-214/demo.json"))
board = {"name": demo["name"], "pcb": demo["pcb"]}

mech = dict(demo["C1"])          # reuse the working step_mapping + placement
board["CR2032_MECH1"] = json.loads(json.dumps(mech))          # top
m2 = json.loads(json.dumps(mech)); m2["is_mirrored"] = True
board["CR2032_MECH2"] = m2                                    # bottom

out = out_dir("mech")
jf = out / "mech_board.json"
jf.write_text(json.dumps(board, indent=1))

logs = []
res = core.generate(
    step_dir=ROOT / "demo/step_files",
    json_file=jf,
    output_dir=out,
    output_name="mech_test",
    log=lambda m: logs.append(m),
)

print("placed:", res.components_placed, " skipped:", res.components_skipped)
print("missing step files:", res.missing_step_files)
step = out / "mech_test.step"
print("STEP written:", step.exists(), step.stat().st_size if step.exists() else 0, "bytes")

# Inspect the assembly tree + count solids to prove the part is shared.
txt = step.read_text(encoding="utf-8", errors="replace")
# The board-name postfix is checked here, not just the bare group name: a bare
# "symbols_top" is what two boards in one CAD session collide on, and a
# substring test for it would keep passing after the postfix was dropped.
for tag in ("symbols_top_mech_test", "symbols_bot_mech_test",
            "CR2032_MECH1", "CR2032_MECH2", "cap_D8x10mm"):
    print(f"  in STEP text: {tag:22} {'YES' if tag in txt else 'no'}")

n = count_solids(read_step(step))
print("solids in shape:", n)

ok = (res.components_placed == 2 and not res.components_skipped
      and "symbols_top_mech_test" in txt and "symbols_bot_mech_test" in txt)
print("\nRESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
