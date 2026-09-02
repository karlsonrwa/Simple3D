# Paths, the output folder, check() and the STEP measuring helpers come from
# tests/_support.py, so the suite runs from wherever the repository is checked
# out and every suite fails the same way. Output goes to build/test-output/.
from _support import ROOT, out_dir, fails, check, rect, volume, read_step

import json, sys
from stepbuilder import core
OUT = out_dir("neg")

print("\n[1] транслитерация s3dLayerIsNegative на реальных слоях")
NEG=["COVERLAY","SOLDERMASK","PASTEMASK"]
def is_neg(name, func=None, keys=NEG):
    probe=((func or "").upper()+" "+(name or "").upper())
    return any(k.upper() in probe for k in keys if k)
for nm,exp in [("COVERLAY_TOP",True),("COVERLAY_BOTTOM",True),("SOLDERMASK_TOP",True),
               ("SOLDERMASK_BOTTOM",True),("PASTEMASK_TOP",True),
               ("STIFFENER_TOP",False),("STIFFENER_TOP2",False),("ADHESIVE_TOP",False),
               ("ADHESIVE_TOP2",False),("ADHESIVE_BOTTOM",False),("TOP",False),("BOTTOM",False)]:
    check(f"{nm} -> {'негатив' if exp else 'позитив'}", is_neg(nm)==exp)
check("функция тоже учитывается", is_neg("MASK_7","Coverlay")==True)
check("список из конфига действует", is_neg("EPOXY_TOP",None,["EPOXY"])==True)

print("\n[2] негативный слой: материал = зона минус шейпы")
base=json.loads((ROOT/"demo/ap-214/demo.json").read_text())
def build(name, negative):
    lay=[{"name":"COVERLAY_TOP","type":"MASK","thickness":0.1,"z_top":0.1,"z_bottom":0.0,
          "negative":negative,"shapes":[{"outline":rect(2,2,6,6),"voids":[]}]},
         {"name":"TOP","type":"CONDUCTOR","thickness":0.05,"z_top":0.0,"z_bottom":-0.05,
          "negative":False,"shapes":None}]
    d={"format":"simple3d","format_version":6,"name":name,
       "pcb":{"thickness":{"soldermask_top":0.0,"board":0.05,"soldermask_bottom":0.0},
              "color":base["pcb"]["color"],"edges":[rect(0,0,10,10)]},
       "stackups":{"S":{"thickness":0.15,"layers":lay}},
       "zones":[{"name":"Z","stackup":"S","contour":rect(0,0,10,10)}]}
    jf=OUT/f"{name}.json"; jf.write_text(json.dumps(d))
    core.generate(step_dir=ROOT/"demo/step_files",json_file=jf,output_dir=OUT,
                  output_name=name,log=lambda m:None)
    return volume(read_step(OUT/f"{name}.step"))
vp=build("pos",False); vn=build("neg",True)
copper=10*10*0.05
check(f"позитив: медь + шейп 4x4x0.1 = {copper+1.6:.2f}", abs(vp-(copper+4*4*0.1))<0.01, f"{vp:.3f}")
check(f"негатив: медь + (100-16)x0.1 = {copper+8.4:.2f}", abs(vn-(copper+(100-16)*0.1))<0.01, f"{vn:.3f}")
check("негатив даёт больше материала, чем позитив", vn>vp)
check("сумма двух = медь*2 + вся зона", abs((vp-copper)+(vn-copper)-100*0.1)<0.01)

print("\n[3] негативный слой без шейпов = сплошной")
lay=[{"name":"COVERLAY_TOP","type":"MASK","thickness":0.1,"z_top":0.1,"z_bottom":0.0,
      "negative":True,"shapes":None}]
d={"format":"simple3d","format_version":6,"name":"nosh",
   "pcb":{"thickness":{"soldermask_top":0.0,"board":0.1,"soldermask_bottom":0.0},
          "color":base["pcb"]["color"],"edges":[rect(0,0,10,10)]},
   "stackups":{"S":{"thickness":0.1,"layers":lay}},
   "zones":[{"name":"Z","stackup":"S","contour":rect(0,0,10,10)}]}
jf=OUT/"nosh.json"; jf.write_text(json.dumps(d))
core.generate(step_dir=ROOT/"demo/step_files",json_file=jf,output_dir=OUT,output_name="nosh",log=lambda m:None)
v=volume(read_step(OUT/"nosh.step"))
check("сплошной слой на всю зону", abs(v-100*0.1)<0.01, f"{v:.3f}")

print("\nРЕЗУЛЬТАТ:", "ВСЁ ПРОЙДЕНО" if not fails else f"{len(fails)} ОШИБОК: {fails}")
sys.exit(0 if not fails else 1)
