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

"""Per-layer stackup build, from the real xsection of the user's board."""
import json, sys
ROOT = _ROOT
sys.path.insert(0, str(ROOT))
from stepbuilder import core
OUT = _OUT / "lay"; OUT.mkdir(exist_ok=True)
fails=[]
def check(n,c,d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}{'' if c else '  <- '+d}"); c or fails.append(n)

def rect(x0,y0,x1,y1):
    return [{"type":"segment","start":[x0,y0],"end":[x1,y0]},
            {"type":"segment","start":[x1,y0],"end":[x1,y1]},
            {"type":"segment","start":[x1,y1],"end":[x0,y1]},
            {"type":"segment","start":[x0,y1],"end":[x0,y0]}]

def layers(spec):
    """spec: [(name,type,thk)] top->bottom. Returns layers with z from core top."""
    idx=[i for i,(n,t,_) in enumerate(spec) if t=="CONDUCTOR"]
    above=sum(t for i,(_,_,t) in enumerate(spec) if i<idx[0])
    out=[];cum=0.0
    for n,t,thk in spec:
        zt=above-cum; zb=zt-thk; cum+=thk
        out.append({"name":n,"type":t,"thickness":thk,"z_top":zt,"z_bottom":zb,"shapes":None})
    return out

FLEX=[("COVERLAY_TOP","MASK",0.025),("ADHESIVE_TOP","MASK",0.05),("TOP","CONDUCTOR",0.045),
      ("DIEL","DIELECTRIC",0.125),("BOTTOM","CONDUCTOR",0.045),
      ("ADHESIVE_BOTTOM","MASK",0.05),("COVERLAY_BOTTOM","MASK",0.025)]
S2=[("STIFFENER_TOP2","MASK",2.0),("ADHESIVE_TOP2","MASK",0.025),("COVERLAY_TOP","MASK",0.025),
    ("ADHESIVE_TOP","MASK",0.05),("SOLDERMASK_TOP","MASK",0.025),("TOP","CONDUCTOR",0.045),
    ("DIEL","DIELECTRIC",0.125),("BOTTOM","CONDUCTOR",0.045),("SOLDERMASK_BOTTOM","MASK",0.025),
    ("ADHESIVE_BOTTOM","MASK",0.05),("COVERLAY_BOTTOM","MASK",0.025)]

print("\n[0] stackups are lined up on the conductors they share")

# Each stackup arrives measured from its OWN first conductor, at z = 0. That is
# a common datum only while every stackup's first conductor is the same physical
# layer. On Cadence's demo board the flex is an INNER pair: FLEXI1 calls INNER1
# z = 0 while PRIMARY has it at -0.5208, the same copper 0.52 mm apart, so the
# flex tail left the rigid board near its top face instead of out of its middle.
RIGID = [("SOLDERMASK_TOP", "MASK", 0.02), ("TOP", "CONDUCTOR", 0.035),
         ("D1", "DIELECTRIC", 0.2), ("INNER1", "CONDUCTOR", 0.035),
         ("D2", "DIELECTRIC", 0.25), ("INNER2", "CONDUCTOR", 0.035),
         ("D3", "DIELECTRIC", 0.2), ("BOTTOM", "CONDUCTOR", 0.035),
         ("SOLDERMASK_BOTTOM", "MASK", 0.02)]
CORE = [("COVERLAY_INNER1", "MASK", 0.025), ("INNER1", "CONDUCTOR", 0.035),
        ("D2", "DIELECTRIC", 0.25), ("INNER2", "CONDUCTOR", 0.035),
        ("COVERLAY_INNER2", "MASK", 0.025)]

pair = {"PRIMARY": {"thickness": 0.83, "layers": layers(RIGID)},
        "FLEXI1": {"thickness": 0.37, "layers": layers(CORE)}}
say = []
lined = core.align_stackups(pair, say.append)


def ztop(st, name):
    return [l for l in lined[st]["layers"] if l["name"] == name][0]["z_top"]


check("before: the two disagree about INNER1",
      abs(pair["PRIMARY"]["layers"][3]["z_top"]
          - pair["FLEXI1"]["layers"][1]["z_top"]) > 0.2)
check("after: INNER1 is one height", abs(ztop("PRIMARY", "INNER1")
                                         - ztop("FLEXI1", "INNER1")) < 1e-12,
      (ztop("PRIMARY", "INNER1"), ztop("FLEXI1", "INNER1")))
check("and so is INNER2", abs(ztop("PRIMARY", "INNER2")
                              - ztop("FLEXI1", "INNER2")) < 1e-12,
      (ztop("PRIMARY", "INNER2"), ztop("FLEXI1", "INNER2")))
check("the rigid stack is the reference and does not move",
      ztop("PRIMARY", "TOP") == 0.0, ztop("PRIMARY", "TOP"))
check("so the flex now sits INSIDE the rigid board, not on top of it",
      ztop("FLEXI1", "COVERLAY_INNER1") < 0.0, ztop("FLEXI1", "COVERLAY_INNER1"))
check("and it says what it moved and by how much",
      any("lined up" in m and "FLEXI1" in m for m in say), say)

# A board whose stackups already agree must not be touched - that is every
# single-stackup board and every rigid-flex one whose flex carries the outer
# copper, which is what the tests below and the whole regression corpus are.
same = {"A": {"thickness": 0.3, "layers": layers(FLEX)},
        "B": {"thickness": 0.3, "layers": layers(FLEX)}}
quiet = []
kept = core.align_stackups(same, quiet.append)
check("stackups that already agree are left alone",
      all(a["z_top"] == b["z_top"] for a, b in
          zip(same["A"]["layers"], kept["A"]["layers"])) and not quiet, quiet)
check("one stackup on its own is left alone",
      core.align_stackups({"A": same["A"]}, quiet.append)["A"] is same["A"])

# Nothing shared to line up by: say so rather than guess.
odd = {"P": {"thickness": 0.3, "layers": layers(RIGID)},
       "Q": {"thickness": 0.2, "layers": layers(
           [("X1", "CONDUCTOR", 0.035), ("DX", "DIELECTRIC", 0.1),
            ("X2", "CONDUCTOR", 0.035)])}}
told = []
core.align_stackups(odd, told.append)
check("a stackup with no shared conductor is reported, not moved",
      any("shares no named conductor" in m for m in told), told)

base=json.loads((ROOT/"demo/ap-214/demo.json").read_text())
def build(name, s2_shape=None):
    st={"FLEX":{"thickness":0.365,"layers":layers(FLEX)},
        "STIFFENER2":{"thickness":2.44,"layers":layers(S2)}}
    if s2_shape is not None:
        for lay in st["STIFFENER2"]["layers"]:
            if lay["name"]=="STIFFENER_TOP2": lay["shapes"]=s2_shape
    d={"format":"simple3d","format_version":6,"name":name,
       "pcb":{"thickness":{"soldermask_top":0.0,"board":0.365,"soldermask_bottom":0.0},
              "color":base["pcb"]["color"],"edges":[rect(0,0,41,26.5)]},
       "stackups":st,
       "zones":[{"name":"S2","stackup":"STIFFENER2","contour":rect(0,0,16,11.38)},
                {"name":"F2","stackup":"FLEX","contour":rect(0,11.38,41,26.5)}]}
    jf=OUT/f"{name}.json"; jf.write_text(json.dumps(d))
    logs=[]
    core.generate(step_dir=ROOT/"demo/step_files",json_file=jf,output_dir=OUT,
                      output_name=name,log=logs.append)
    from OCP.STEPControl import STEPControl_Reader
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    r=STEPControl_Reader(); r.ReadFile(str(OUT/f"{name}.step")); r.TransferRoots()
    s=r.OneShape(); g=GProp_GProps(); BRepGProp.VolumeProperties_s(s,g)
    bb=Bnd_Box(); BRepBndLib.Add_s(s,bb)
    return g.Mass(), bb, logs, (OUT/f"{name}.step").stat().st_size

print("\n[1] слои без шейпов -> зона целиком (как раньше), Z верны")
v1,bb1,logs1,sz1 = build("nolay")
check("верх платы = 0 (датум top)", abs(bb1.CornerMax().Z())<1e-6, str(bb1.CornerMax().Z()))
check("низ = -2.44", abs(bb1.CornerMin().Z()+2.44)<1e-6, str(bb1.CornerMin().Z()))
want = 16*11.38*2.44 + 41*15.12*0.365
check(f"объём {v1:.3f} = сумма зон {want:.3f}", abs(v1-want)/want<0.001, f"{v1:.3f}")
check("лог сообщает число тел слоёв", any("layer solid(s)" in m for m in logs1), str(logs1[:8]))

print("\n[2] у стифнера свой шейп меньше зоны -> объём падает ровно на разницу")
# шейп 86.763 mm2 против зоны 16x11.38=182.08
sq=[{"outline":rect(1,1,10.315,10.315),"voids":[]}]   # 9.315^2 = 86.769 mm2
v2,bb2,logs2,sz2 = build("withshape", s2_shape=sq)
lost = (16*11.38 - 9.315*9.315)*2.0
check(f"объём упал на {v1-v2:.3f} = площадь x 2.0мм = {lost:.3f}",
      abs((v1-v2)-lost)/lost < 0.001, f"{v1-v2:.3f} vs {lost:.3f}")
check("габарит Z не изменился", abs(bb2.CornerMax().Z()-bb1.CornerMax().Z())<1e-6)

print("\n[3] пустота в шейпе становится отверстием")
ring=[{"outline":rect(1,1,10.315,10.315),"voids":[rect(4,4,7,7)]}]
v3,bb3,_,_ = build("withvoid", s2_shape=ring)
check("объём меньше ещё на 3x3x2.0=18.0", abs((v2-v3)-18.0)<0.01, f"{v2-v3:.3f}")

print("\n[4] шейп обрезается контуром зоны")
big=[{"outline":rect(-50,-50,50,50),"voids":[]}]     # намного больше зоны
v4,_,logs4,_ = build("clip", s2_shape=big)
check("объём как у зоны целиком (обрезано)", abs(v4-v1)/v1<0.001, f"{v4:.3f} vs {v1:.3f}")
check("нет предупреждения об обрезке", not [m for m in logs4 if "unclipped" in m])

print("\n[5] сплавление: одно тело, файл меньше компаунда")
from OCP.STEPControl import STEPControl_Reader
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID
r=STEPControl_Reader(); r.ReadFile(str(OUT/"nolay.step")); r.TransferRoots()
e=TopExp_Explorer(r.OneShape(),TopAbs_SOLID); n=0
while e.More(): n+=1; e.Next()
check(f"плата + компонентов = {n} тел (не 18 отдельных слоёв)", n<=3, str(n))

print("\n[6] обычная плата не затронута")
d2=json.loads(json.dumps(json.loads((OUT/"nolay.json").read_text())))
d2.pop("stackups"); d2.pop("zones")
d2["pcb"]["thickness"]={"soldermask_top":0.03,"board":1.036,"soldermask_bottom":0.03}
f2=OUT/"plain.json"; f2.write_text(json.dumps(d2))
lg=[]
core.generate(step_dir=ROOT/"demo/step_files",json_file=f2,output_dir=OUT,
              output_name="plain",log=lg.append)
check("нет послойного лога", not [m for m in lg if "layer solid" in m])
r2=STEPControl_Reader(); r2.ReadFile(str(OUT/"plain.step")); r2.TransferRoots()
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
g2=GProp_GProps(); BRepGProp.VolumeProperties_s(r2.OneShape(),g2)
check("объём = контур x 1.096", abs(g2.Mass()-41*26.5*1.096)/(41*26.5*1.096)<1e-6, f"{g2.Mass():.3f}")

print("\nРЕЗУЛЬТАТ:", "ВСЁ ПРОЙДЕНО" if not fails else f"{len(fails)} ОШИБОК: {fails}")
sys.exit(0 if not fails else 1)
