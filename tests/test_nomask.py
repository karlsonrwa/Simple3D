# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, rect, volume, read_step

import json, sys
from stepbuilder import core
OUT = out_dir("nomask")

# РЕАЛЬНЫЙ STIFFENER2 с платы пользователя
S2=[("STIFFENER_TOP2","MASK",2.0),("ADHESIVE_TOP2","MASK",0.025),("COVERLAY_TOP","MASK",0.025),
    ("ADHESIVE_TOP","MASK",0.05),("SOLDERMASK_TOP","MASK",0.025),("TOP","CONDUCTOR",0.045),
    ("DIEL","DIELECTRIC",0.125),("BOTTOM","CONDUCTOR",0.045),("SOLDERMASK_BOTTOM","MASK",0.025),
    ("ADHESIVE_BOTTOM","MASK",0.05),("COVERLAY_BOTTOM","MASK",0.025)]
def mk(spec):
    return [{"name":n,"type":t,"thickness":thk,"z_top":0,"z_bottom":0,
             "negative":False,"function":None,"shapes":None} for n,t,thk in spec]

print("\n[1] restack: пересчёт z, ядро на нуле")
L=core.restack(mk(S2))
by={l["name"]:l for l in L}
check("STIFFENER_TOP2 верх = 2.125", abs(by["STIFFENER_TOP2"]["z_top"]-2.125)<1e-9, str(by["STIFFENER_TOP2"]["z_top"]))
check("верх меди TOP = 0", abs(by["TOP"]["z_top"])<1e-9)
check("низ COVERLAY_BOTTOM = -0.315", abs(by["COVERLAY_BOTTOM"]["z_bottom"]+0.315)<1e-9)
check("полная толщина 2.44", abs(max(l['z_top'] for l in L)-min(l['z_bottom'] for l in L)-2.44)<1e-9)

print("\n[2] маска убрана -> стек смыкается к ядру")
st={"S2":{"thickness":2.44,"layers":L}}
out=core.drop_soldermask(st, log=lambda m: None)
L2=out["S2"]["layers"]; by2={l["name"]:l for l in L2}
check("слоёв стало на 2 меньше", len(L2)==len(L)-2, f"{len(L)} -> {len(L2)}")
check("SOLDERMASK_TOP исчез", "SOLDERMASK_TOP" not in by2)
check("SOLDERMASK_BOTTOM исчез", "SOLDERMASK_BOTTOM" not in by2)
check("ядро не сдвинулось: верх TOP = 0", abs(by2["TOP"]["z_top"])<1e-9, str(by2["TOP"]["z_top"]))
check("ядро цело: низ BOTTOM = -0.215", abs(by2["BOTTOM"]["z_bottom"]+0.215)<1e-9)
check("верхняя часть осела ровно на 0.025",
      abs((by["STIFFENER_TOP2"]["z_top"]-by2["STIFFENER_TOP2"]["z_top"])-0.025)<1e-9,
      f"{by['STIFFENER_TOP2']['z_top']} -> {by2['STIFFENER_TOP2']['z_top']}")
check("нижняя часть поднялась ровно на 0.025",
      abs((by2["COVERLAY_BOTTOM"]["z_bottom"]-by["COVERLAY_BOTTOM"]["z_bottom"])-0.025)<1e-9,
      f"{by['COVERLAY_BOTTOM']['z_bottom']} -> {by2['COVERLAY_BOTTOM']['z_bottom']}")
check("между ADHESIVE_TOP и медью нет щели",
      abs(by2["ADHESIVE_TOP"]["z_bottom"]-by2["TOP"]["z_top"])<1e-9,
      f"{by2['ADHESIVE_TOP']['z_bottom']} vs {by2['TOP']['z_top']}")
check("между медью BOTTOM и ADHESIVE_BOTTOM нет щели",
      abs(by2["BOTTOM"]["z_bottom"]-by2["ADHESIVE_BOTTOM"]["z_top"])<1e-9)
check("толщина 2.44 - 0.05 = 2.39",
      abs(max(l['z_top'] for l in L2)-min(l['z_bottom'] for l in L2)-2.39)<1e-9)

print("\n[3] распознавание маски по написанию и по IPC-функции")
for nm,fn,exp in [("SOLDERMASK_TOP",None,True),("SOLDER_MASK_TOP",None,True),
                  ("SM_TOP","Solder Mask",True),("MASK_3","SolderMask",True),
                  ("COVERLAY_TOP",None,False),("ADHESIVE_TOP",None,False),
                  ("STIFFENER_TOP2",None,False),("TOP",None,False)]:
    check(f"{nm}/{fn} -> {'маска' if exp else 'не маска'}",
          core._is_soldermask({"name":nm,"function":fn})==exp)

print("\n[4] сборка целиком: плата тоньше ровно на маску")
base=json.loads((ROOT/"demo/ap-214/demo.json").read_text())
def build(name, ignore):
    d={"format":"simple3d","format_version":6,"name":name,
       "pcb":{"thickness":{"soldermask_top":0.0,"board":2.44,"soldermask_bottom":0.0},
              "color":base["pcb"]["color"],"edges":[rect(0,0,10,10)]},
       "stackups":{"S2":{"thickness":2.44,"layers":core.restack(mk(S2))}},
       "zones":[{"name":"Z","stackup":"S2","contour":rect(0,0,10,10)}]}
    jf=OUT/f"{name}.json"; jf.write_text(json.dumps(d))
    logs=[]
    core.generate(step_dir=ROOT/"demo/step_files",json_file=jf,output_dir=OUT,
                  output_name=name,ignore_soldermask=ignore,log=logs.append)
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    s=read_step(OUT/f"{name}.step")
    bb=Bnd_Box(); BRepBndLib.Add_s(s,bb)
    return volume(s), bb, logs
v1,bb1,_ = build("with",False)
v2,bb2,lg = build("without",True)
check(f"объём {v1:.2f} -> {v2:.2f}, разница = 100x0.05", abs((v1-v2)-100*0.05)<0.01, f"{v1-v2:.3f}")
check("габарит по Z: 2.44 -> 2.39",
      abs((bb2.CornerMax().Z()-bb2.CornerMin().Z())-2.39)<1e-6,
      f"{bb2.CornerMax().Z()-bb2.CornerMin().Z():.4f}")
check("лог называет убранные слои", any("SOLDERMASK_TOP" in m and "Ignoring soldermask" in m for m in lg), str([m for m in lg if "soldermask" in m.lower()]))

print("\n[5] обычная плата: маска тоже уходит из толщины")
d2={"format":"simple3d","format_version":6,"name":"plain",
    "pcb":{"thickness":{"soldermask_top":0.03,"board":1.036,"soldermask_bottom":0.03},
           "color":base["pcb"]["color"],"edges":[rect(0,0,10,10)]}}
f2=OUT/"plain.json"; f2.write_text(json.dumps(d2))
for nm,ig,want in [("p_with",False,1.096),("p_without",True,1.036)]:
    core.generate(step_dir=ROOT/"demo/step_files",json_file=f2,output_dir=OUT,
                  output_name=nm,ignore_soldermask=ig,log=lambda m:None)
    v=volume(read_step(OUT/f"{nm}.step"))
    check(f"{'без' if ig else 'с'} маской: толщина {want}", abs(v-100*want)<0.01, f"{v/100:.4f}")

print("\n[6] format_version 9 без pcb.thickness: маска уходит из толщины, измеренной по стеку")
# Раунд 79, план E2: толщина берётся из стека по положению слоёв, и
# ignore_soldermask действует на неё так же, как на записанную.
d3={"format":"simple3d","format_version":9,"name":"plain9",
    "pcb":{"color":base["pcb"]["color"],"edges":[rect(0,0,10,10)]},
    "stackups":{"Primary":{"thickness":1.096,"layers":[
        {"name":"SOLDERMASK_TOP","type":"MASK","thickness":0.03,"z_top":0.03,"z_bottom":0.0,"negative":True,"function":"SOLDER_MASK","shapes":None},
        {"name":"TOP","type":"CONDUCTOR","thickness":0.035,"z_top":0.0,"z_bottom":-0.035,"negative":False,"function":"CONDUCTOR","shapes":None},
        {"name":None,"type":"DIELECTRIC","thickness":0.966,"z_top":-0.035,"z_bottom":-1.001,"negative":False,"function":None,"shapes":None},
        {"name":"BOTTOM","type":"CONDUCTOR","thickness":0.035,"z_top":-1.001,"z_bottom":-1.036,"negative":False,"function":"CONDUCTOR","shapes":None},
        {"name":"SOLDERMASK_BOTTOM","type":"MASK","thickness":0.03,"z_top":-1.036,"z_bottom":-1.066,"negative":True,"function":"SOLDER_MASK","shapes":None}]}},
    "components":{}}
f3=OUT/"plain9.json"; f3.write_text(json.dumps(d3))
for nm,ig,want in [("p9_with",False,1.096),("p9_without",True,1.036)]:
    core.generate(step_dir=ROOT/"demo/step_files",json_file=f3,output_dir=OUT,
                  output_name=nm,ignore_soldermask=ig,log=lambda m:None)
    v=volume(read_step(OUT/f"{nm}.step"))
    check(f"v9 {'без' if ig else 'с'} маской: толщина {want}", abs(v-100*want)<0.01, f"{v/100:.4f}")

print("\nРЕЗУЛЬТАТ:", "ВСЁ ПРОЙДЕНО" if not fails else f"{len(fails)} ОШИБОК: {fails}")
sys.exit(0 if not fails else 1)
