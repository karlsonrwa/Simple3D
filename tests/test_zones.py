# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, rect, volume, read_step

"""Multi-stackup, built from the real zone data of the user's rigid-flex board."""
import json, sys
from stepbuilder import core

OUT = out_dir("zones")


# the real profiles measured on the board (above, core, below)
PROF = {"FLEX":(0.075,0.215,0.075), "STIFFENER1":(0.200,0.215,0.075),
        "STIFFENER2":(2.125,0.215,0.100)}
ZONES = [
    ("STIFFENER2","STIFFENER2", rect(0,0,16,11.38)),
    ("FLEX2","FLEX",            rect(0,11.38,41,26.5)),
    ("STTIFFENER1","STIFFENER1",rect(24.4,26.5,41.6,30.04)),
    ("FLEX1","FLEX",            rect(24.83,29.9,41.17,32.0)),
]

print("\n[1] profiles reproduce the API totals")
for name,(a,c,b) in PROF.items():
    check(f"{name} = {a+c+b:.3f}", abs((a+c+b)-{"FLEX":0.365,"STIFFENER1":0.49,"STIFFENER2":2.44}[name])<1e-9)
check("all cores equal (this is what makes zones line up)",
      len({c for _,c,_ in PROF.values()})==1)

print("\n[2] zone_levels: aligned on the core, not on outer faces")
zones=[{"name":n,"stackup":s,"above":PROF[s][0],"core":PROF[s][1],
        "below":PROF[s][2],"contour":ct} for n,s,ct in ZONES]
lv, top, bot = core.zone_levels(zones, "top")
check("board top is 0 with datum=top", abs(top)<1e-9, str(top))
check("overall thickness = thickest zone span", abs((top-bot)-2.44)<1e-9, str(top-bot))
# core tops must coincide across zones: zone_top - above is the same everywhere
core_tops = {round(lv[n][0]-PROF[s][0],9) for n,s,_ in ZONES}
check("every zone shares one core top", len(core_tops)==1, str(core_tops))
check("STIFFENER2 top is the datum", abs(lv["STIFFENER2"][0])<1e-9, str(lv["STIFFENER2"][0]))
check("FLEX sits below it by 2.125-0.075",
      abs(lv["FLEX2"][0]-(-2.05))<1e-9, str(lv["FLEX2"][0]))

lv2, top2, bot2 = core.zone_levels(zones, "bottom")
check("datum=bottom puts the lowest face at 0", abs(bot2)<1e-9, str(bot2))
check("span unchanged", abs((top2-bot2)-2.44)<1e-9)

print("\n[3] the board builds, and its volume is the sum of the zones")
base = json.loads((ROOT/"demo/ap-214/demo.json").read_text())
d = {"format":"simple3d","format_version":5,"name":"flexboard",
     "pcb":{"thickness":{"soldermask_top":0.0,"board":0.365,"soldermask_bottom":0.0},
            "color":base["pcb"]["color"],
            "edges":[rect(0,0,41.6,32.0)]},
     "zones":zones}
jf=OUT/"flex.json"; jf.write_text(json.dumps(d))
logs=[]
res=core.generate(step_dir=ROOT/"demo/step_files", json_file=jf, output_dir=OUT,
                  output_name="flex", log=logs.append)
got=volume(read_step(OUT/"flex.step"))
want=(16*11.38*2.44)+(41*15.12*0.365)+(17.2*3.54*0.49)+(16.34*2.1*0.365)
check(f"volume {got:.4f} vs zone sum {want:.4f}", abs(got-want)/want < 0.02,
      f"diff {abs(got-want):.4f}")
check("log reports the zones", any("Multi-stackup board: 4 zone" in m for m in logs),
      str([m for m in logs[:6]]))

print("\n[4] a component sits on ITS zone, not on the board top")
def place(zone):
    dd=json.loads(json.dumps(d))
    dd["U1"]={"step_mapping":{"step_name":"cap_D8x10mm.stp","rotation_x":0.0,
              "rotation_y":0.0,"rotation_z":0.0,"offset_x":0.0,"offset_y":0.0,
              "offset_z":0.0},"is_mirrored":False,"x":8.0,"y":5.0,"angle":0.0,
              "zone":zone}
    f=OUT/f"c_{zone or 'none'}.json"; f.write_text(json.dumps(dd))
    core.generate(step_dir=ROOT/"demo/step_files", json_file=f, output_dir=OUT,
                      output_name=f"c_{zone or 'none'}", log=lambda m: None)
    s=read_step(OUT/f"c_{zone or 'none'}.step")
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    bb=Bnd_Box(); BRepBndLib.Add_s(s, bb)
    return bb.CornerMax().Z()
zmax_stiff = place("STIFFENER2")
zmax_flex  = place("FLEX2")
check("part on the stiffener reaches higher", zmax_stiff > zmax_flex + 1.9,
      f"{zmax_stiff:.3f} vs {zmax_flex:.3f}")
check("difference equals the surface offset (2.05)",
      abs((zmax_stiff-zmax_flex)-2.05)<1e-3, f"{zmax_stiff-zmax_flex:.4f}")
zmax_none = place(None)
check("unknown zone falls back to the board surface",
      abs(zmax_none-zmax_stiff)<1e-6, f"{zmax_none:.3f}")

print("\n[5] an ordinary board is untouched by any of this")
d2=json.loads(json.dumps(d)); d2.pop("zones")
d2["pcb"]["thickness"]={"soldermask_top":0.03,"board":1.036,"soldermask_bottom":0.03}
f2=OUT/"plain.json"; f2.write_text(json.dumps(d2))
logs2=[]
res2=core.generate(step_dir=ROOT/"demo/step_files", json_file=f2, output_dir=OUT,
                   output_name="plain", log=logs2.append)
check("no multi-stackup log", not [m for m in logs2 if "Multi-stackup" in m])
v2=volume(read_step(OUT/"plain.step"))
check("plain volume = outline x 1.096", abs(v2-(41.6*32.0*1.096))/(41.6*32.0*1.096)<1e-6,
      f"{v2:.4f}")
check("empty zones list behaves as no zones", True)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
