# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, rect, volume, read_step, count_solids

"""Body stitching must work on an ORDINARY single-stackup board too."""
import json, sys

from skill_transliterations import in_body
from stepbuilder import core
OUT = out_dir("plainmodes")
# a plain 2-layer board, exactly what axlXSectionGet(nil 'all) would give
PRIMARY=[("SILKSCREEN_TOP","MASK",0.0),("SOLDERMASK_TOP","MASK",0.025),
         ("TOP","CONDUCTOR",0.045),("DIEL","DIELECTRIC",0.964),
         ("BOTTOM","CONDUCTOR",0.045),("SOLDERMASK_BOTTOM","MASK",0.025)]
def mk(spec):
    return core.restack([{"name":n,"type":t,"thickness":k,"z_top":0,"z_bottom":0,
                          "negative":False,"function":None,"shapes":None} for n,t,k in spec])
base=json.loads((ROOT/"demo/ap-214/demo.json").read_text())
def build(name, mode, with_stackups=True):
    d={"format":"simple3d","format_version":6,"name":name,
       "pcb":{"thickness":{"soldermask_top":0.025,"board":1.054,"soldermask_bottom":0.025},
              "color":base["pcb"]["color"],"edges":[rect(0,0,20,10)]}}
    if with_stackups:
        d["stackups"]={"Primary":{"thickness":1.104,"layers":mk(PRIMARY)}}
    jf=OUT/f"{name}.json"; jf.write_text(json.dumps(d))
    logs=[]
    core.generate(step_dir=ROOT/"demo/step_files",json_file=jf,output_dir=OUT,
                  output_name=name,board_mode=mode,log=logs.append)
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    s=read_step(OUT/f"{name}.step")
    bb=Bnd_Box(); BRepBndLib.Add_s(s,bb)
    return count_solids(s),volume(s),bb,logs

print("\n[1] Solid on a plain board: the single-prism path, untouched")
n,v,bb,lg=build("p_solid","solid")
check("one solid", n==1, str(n))
check("volume = outline x 1.104", abs(v-20*10*1.104)<0.01, f"{v:.3f}")
check("no zone log", not [m for m in lg if "one zone" in m], str(lg[:4]))

print("\n[2] Not stitched on a plain board now separates the layers")
n2,v2,bb2,lg2=build("p_inspect","inspect")
check("many parts", n2>=5, str(n2))
check("log says it built one zone", any("one zone" in m for m in lg2), str(lg2[:4]))
check("same volume as solid", abs(v2-v)<0.01, f"{v2:.3f} vs {v:.3f}")
check("same Z extent", abs((bb2.CornerMax().Z()-bb2.CornerMin().Z())-1.104)<1e-6,
      f"{bb2.CornerMax().Z()-bb2.CornerMin().Z():.4f}")

print("\n[3] Solid colored layers on a plain board")
n3,v3,bb3,lg3=build("p_layers","layers")
check("one solid", n3==1, str(n3))
check("same volume", abs(v3-v)<0.02, f"{v3:.3f} vs {v:.3f}")
check("log mentions faces coloured", any("coloured" in m or "colored" in m for m in lg3),
      str([m for m in lg3 if "face" in m]))

print("\n[3b] format_version 9: pcb.thickness may be absent, and the stackup wins a disagreement")
# Round 79, plan E2. Without pcb.thickness the reader measures the board from
# its stackup by position - the exporter's own rule - and says so; with a
# pcb.thickness that disagrees with the stackup by more than a micron the
# stackup wins, with a warning (an intermediate exported before round 76
# carried the combined view's number on a rigid-flex board).
def build9(name, mode, thickness):
    d={"format":"simple3d","format_version":9,"name":name,
       "pcb":{"color":base["pcb"]["color"],"edges":[rect(0,0,20,10)]},
       "stackups":{"Primary":{"thickness":1.104,"layers":mk(PRIMARY)}},"components":{}}
    if thickness is not None:
        d["pcb"]["thickness"]=thickness
    jf=OUT/f"{name}.json"; jf.write_text(json.dumps(d))
    logs=[]
    core.generate(step_dir=ROOT/"demo/step_files",json_file=jf,output_dir=OUT,
                  output_name=name,board_mode=mode,log=logs.append)
    s=read_step(OUT/f"{name}.step")
    return volume(s),logs
v9,lg9=build9("p_nothick","solid",None)
check("no pcb.thickness: the solid is 1.104 thick, measured from the stackup", abs(v9-20*10*1.104)<0.01, f"{v9:.3f}")
check("and the log says so", any(m.startswith("note:") and "measured from stackup Primary" in m for m in lg9), str(lg9[:3]))
v9b,lg9b=build9("p_wrongthick","solid",{"soldermask_top":0.0,"board":0.5,"soldermask_bottom":0.0})
check("a pcb.thickness that disagrees with the stackup loses to it", abs(v9b-20*10*1.104)<0.01, f"{v9b:.3f}")
check("with a warning that names both numbers", any(m.startswith("warning:") and "0.500" in m and "1.104" in m for m in lg9b), str(lg9b[:3]))
v9c,lg9c=build9("p_samethick","solid",{"soldermask_top":0.025,"board":1.054,"soldermask_bottom":0.025})
check("one that agrees is used without a word", abs(v9c-20*10*1.104)<0.01 and not [m for m in lg9c if "pcb.thickness" in m], str(lg9c[:3]))

print("\n[4] an OLD json with no stackups says so instead of silently doing nothing")
n4,v4,bb4,lg4=build("p_old","inspect",with_stackups=False)
check("falls back to one solid", n4==1, str(n4))
check("warns, naming the mode and the fix",
      any(m.startswith("warning:") and "re-export" in m for m in lg4), str(lg4[:4]))

print(chr(10) + "[5] silkscreen and paste never enter the body")
FULL = [("SILKSCREEN_TOP","SILKSCREEN"),("PASTEMASK_TOP","SOLDER_PASTE"),
        ("SOLDERMASK_TOP","SOLDER_MASK"),("TOP","CONDUCTOR"),("","DIELECTRIC"),
        ("BOTTOM","CONDUCTOR"),("SOLDERMASK_BOTTOM","SOLDER_MASK"),
        ("PASTEMASK_BOTTOM","SOLDER_PASTE"),("SILKSCREEN_BOTTOM","SILKSCREEN")]
kept = [n for n, f in FULL if in_body(n, f)]
check("silkscreen dropped", not [n for n in kept if "SILK" in n], str(kept))
check("pastemask dropped", not [n for n in kept if "PASTE" in n], str(kept))
check("soldermask kept", len([n for n in kept if "SOLDERMASK" in n]) == 2, str(kept))
check("copper kept", len([n for n in kept if n in ("TOP","BOTTOM")]) == 2, str(kept))
check("dielectric kept", "" in kept, str(kept))
check("a layer named SOLDERMASK is not caught by the paste test",
      in_body("SOLDERMASK_TOP", "SOLDER_MASK"))
# The same filter runs for named (rigid-flex) stackups: s3dStackupJson is the
# only emitter and both call sites go through it. A FLEX stack that does carry
# paste and legend must lose exactly those and keep everything else.
FLEXP = [("SILKSCREEN_TOP","SILKSCREEN"),("STIFFENER_TOP",""),("ADHESIVE_TOP2",""),
         ("COVERLAY_TOP",""),("PASTEMASK_TOP","SOLDER_PASTE"),("ADHESIVE_TOP",""),
         ("SOLDERMASK_TOP","SOLDER_MASK"),("TOP","CONDUCTOR"),("","DIELECTRIC"),
         ("BOTTOM","CONDUCTOR"),("SOLDERMASK_BOTTOM","SOLDER_MASK"),
         ("ADHESIVE_BOTTOM",""),("COVERLAY_BOTTOM",""),
         ("PASTEMASK_BOTTOM","SOLDER_PASTE"),("SILKSCREEN_BOTTOM","SILKSCREEN")]
fkept = [n for n, f in FLEXP if in_body(n, f)]
check("flex: paste gone from both sides",
      not [n for n in fkept if "PASTE" in n], str(fkept))
check("flex: legend gone from both sides", not [n for n in fkept if "SILK" in n])
check("flex: coverlay, adhesive, stiffener, soldermask all kept",
      len([n for n in fkept if "COVERLAY" in n]) == 2
      and len([n for n in fkept if "ADHESIVE" in n]) == 3
      and any("STIFFENER" in n for n in fkept)
      and len([n for n in fkept if "SOLDERMASK" in n]) == 2, str(fkept))
# names a design might use without setting a layerFunction
for nm, want in [("PASTE_TOP", False), ("SILK_TOP", False), ("COVERLAY_TOP", True),
                 ("STIFFENER_TOP2", True), ("SOLDERMASK_TOP", True)]:
    check(f"bare name {nm} -> {'body' if want else 'dropped'}",
          in_body(nm, "") == want)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(0 if not fails else 1)
