# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, read_step, count_solids, entity_count

"""A JSON whose component keys are synthetic mechanical names (CR2032_MECH1 /
_MECH2, no refdes) must build and place under symbols_top and symbols_bot -
and the model behind them must be imported ONCE however many refdes reference
it, which is what `ModelCache.labels_for` is for.

Until 2026-09-15 this suite printed `solids in shape: N` and compared it to
nothing: cutting the cache so every refdes re-imported its model left it, and
every other geometric suite, green (docs/test-audit.md, finding 2). It also
never went through `_support.check`, so it contributed no PASS/FAIL line to
the suite at all. Both are fixed here, and the oracle is the one that moves:
the number of solid bodies WRITTEN, which a shared part holds constant while
the number of placements grows.

`count_solids` is not that oracle and cannot be: OneShape expands every
instance, so it reads 26 for five placements whether the part is shared or
copied. It is kept below to say the placements are really there.
"""
import json, sys

# The PACKAGE import, not a bare `core`: core.py reaches sideways to its
# siblings (`from .colors import ...`, `from .bend import ...`) inside the
# functions that need them, and a bare module has no package to reach from.
# The failure is an ImportError deep in generate(), on whichever feature the
# test happens to exercise.
from stepbuilder import core

demo = json.load(open(ROOT / "demo/ap-214/demo.json"))
out = out_dir("mech")

# The model all the mechanical components below share. Named here because the
# sharing checks count the log line that reads it.
MODEL = demo["C1"]["step_mapping"]["step_name"]


def build(name, copies):
    """A board of `copies` mechanical components, all on the same model.

    Alternately mirrored, so they land on both sides - top and bottom are two
    different transforms of ONE imported part, not two imports.
    """
    board = {"name": demo["name"], "pcb": demo["pcb"]}
    for i in range(copies):
        comp = json.loads(json.dumps(demo["C1"]))    # working step_mapping + placement
        comp["is_mirrored"] = bool(i % 2)
        board[f"CR2032_MECH{i + 1}"] = comp
    jf = out / f"{name}.json"
    jf.write_text(json.dumps(board, indent=1))
    logs = []
    res = core.generate(step_dir=ROOT / "demo/step_files", json_file=jf,
                        output_dir=out, output_name=name,
                        log=lambda m: logs.append(m))
    step = out / f"{name}.step"
    return res, logs, step, step.read_text(encoding="utf-8", errors="replace")


print("\n[1] mechanical names build, place and reach both sides")
res, logs, step, txt = build("mech_test", 2)
check("both placed", res.components_placed == 2, res.components_placed)
check("none skipped", not res.components_skipped, res.components_skipped)
check("no missing model files", not res.missing_step_files, res.missing_step_files)
check("STEP written", step.exists() and step.stat().st_size > 0,
      step.stat().st_size if step.exists() else "absent")

# The board-name postfix is checked here, not just the bare group name: a bare
# "symbols_top" is what two boards in one CAD session collide on, and a
# substring test for it would keep passing after the postfix was dropped.
for tag in ("symbols_top_mech_test", "symbols_bot_mech_test", "cap_D8x10mm"):
    check(f"{tag} in the STEP text", tag in txt)
check("the bare group name is not written without the board postfix",
      "'symbols_top'" not in txt and "'symbols_bot'" not in txt)

# The refdes itself is deliberately NOT a name in the file: the instance under
# symbols_* carries the model's name and nothing wraps it (core.py, "no
# per-refdes wrapper sub-assembly and no refdes_<board> instance name"). The
# old suite printed YES/no for these two and compared them to nothing, which
# read as a defect; it is the design. Asserted so that bringing the wrapper
# back is a decision someone makes here rather than a silent change.
check("no per-refdes name is written for either component",
      "CR2032_MECH1" not in txt and "CR2032_MECH2" not in txt,
      [t for t in ("CR2032_MECH1", "CR2032_MECH2") if t in txt])

print("\n[2] the model is imported once, not once per refdes")

# Five copies of the same component against two. A shared part writes the
# model's bodies ONCE, so the solid geometry in the file does not grow; only
# the assembly tree does. Cut `ModelCache.labels_for`'s first line and the
# five-copy file carries five copies of the geometry instead.
res5, logs5, step5, txt5 = build("mech_five", 5)
check("five placed", res5.components_placed == 5, res5.components_placed)

reads2 = [m for m in logs if m == f"Reading {MODEL}"]
reads5 = [m for m in logs5 if m == f"Reading {MODEL}"]
check(f"{MODEL} read once for two refdes", len(reads2) == 1, logs)
check(f"{MODEL} read once for five refdes", len(reads5) == 1,
      [m for m in logs5 if m.startswith("Reading")])

breps2, breps5 = txt.count("MANIFOLD_SOLID_BREP"), txt5.count("MANIFOLD_SOLID_BREP")
shells2, shells5 = txt.count("CLOSED_SHELL"), txt5.count("CLOSED_SHELL")
check(f"the solid bodies written do not grow with the placements "
      f"({breps2} for two, {breps5} for five)", breps2 == breps5, (breps2, breps5))
check(f"nor do their shells ({shells2}, {shells5})", shells2 == shells5,
      (shells2, shells5))

# ...while the placements themselves plainly do, which is what says the file
# really does carry five components and not two. One board body plus the
# model's own solids per placement.
solids2, solids5 = count_solids(read_step(step)), count_solids(read_step(step5))
per = (solids2 - 1) // 2
check(f"the instances do grow ({solids2} solids for two, {solids5} for five)",
      solids5 > solids2, (solids2, solids5))
check(f"five placements of a {per}-solid model on one board body give "
      f"{1 + 5 * per}", solids5 == 1 + 5 * per, (solids2, solids5, per))

occ2, occ5 = (txt.count("NEXT_ASSEMBLY_USAGE_OCCURRENCE"),
              txt5.count("NEXT_ASSEMBLY_USAGE_OCCURRENCE"))
check(f"and the assembly tree grows by exactly three occurrences ({occ2} -> {occ5})",
      occ5 - occ2 == 3, (occ2, occ5))

ents2, ents5 = entity_count(step), entity_count(step5)
check(f"three more placements cost {ents5 - ents2} entities, not another copy of "
      f"the model ({ents2} -> {ents5})", ents5 - ents2 < ents2 // 10,
      (ents2, ents5))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
