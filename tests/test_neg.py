# Paths are derived from this file's own location, so the suite runs from
# wherever the repository is checked out. Anything a test writes goes to
# build/test-output/, which is gitignored.
import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parent.parent
_OUT = _ROOT / "build" / "test-output"
_OUT.mkdir(parents=True, exist_ok=True)
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import json, sys
from pathlib import Path
ROOT=_ROOT; sys.path.insert(0,str(ROOT))
from stepbuilder import core
OUT=_OUT / "neg"; OUT.mkdir(exist_ok=True)
fails=[]
def check(n,c,d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}{'' if c else '  <- '+d}"); c or fails.append(n)
def rect(a,b,c,d):
    return [{"type":"segment","start":[a,b],"end":[c,b]},{"type":"segment","start":[c,b],"end":[c,d]},
            {"type":"segment","start":[c,d],"end":[a,d]},{"type":"segment","start":[a,d],"end":[a,b]}]

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
    from OCP.STEPControl import STEPControl_Reader
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    r=STEPControl_Reader(); r.ReadFile(str(OUT/f"{name}.step")); r.TransferRoots()
    g=GProp_GProps(); BRepGProp.VolumeProperties_s(r.OneShape(),g); return g.Mass()
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
from OCP.STEPControl import STEPControl_Reader
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
r=STEPControl_Reader(); r.ReadFile(str(OUT/"nosh.step")); r.TransferRoots()
g=GProp_GProps(); BRepGProp.VolumeProperties_s(r.OneShape(),g)
check("сплошной слой на всю зону", abs(g.Mass()-100*0.1)<0.01, f"{g.Mass():.3f}")

print("\nРЕЗУЛЬТАТ:", "ВСЁ ПРОЙДЕНО" if not fails else f"{len(fails)} ОШИБОК: {fails}")
sys.exit(0 if not fails else 1)
