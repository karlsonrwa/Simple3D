"""The OCP names that cadquery-ocp 8.0 (OCCT 8) spells differently from 7.9,
bound once under their 7.9 names, and the one call whose behaviour changed.

Measured on 2026-09-21 (round 90) with cadquery-ocp 7.9.3.1.1 and 8.0.1.0.0
side by side, after the same three changes had broken step2html:

- every NCollection instantiation moved out of the per-package modules into
  one module, `OCP.collections`, named after its template arguments. So
  `OCP.TopTools.TopTools_ListOfShape` is `OCP.collections.List_TopoDS_Shape`
  there, and `OCP.TopTools` no longer has the old name at all. Seven such
  names are used here; `OCP.collections` does not exist in 7.9;
- `TopoDS.Face_s`, `Wire_s`, `Edge_s`, `Solid_s`, `Shell_s` lost their
  suffix. The bare `TopoDS.Face(...)` exists in both, so the code spells the
  casts bare and nothing here is needed for them. Every OTHER `_s` static the
  pipeline calls - `BRepGProp.VolumeProperties_s`, `TDataStd_Name.Set_s`,
  `BRepBndLib.Add_s`, `TopExp.MapShapes_s` and fifteen more - survived 8.0
  unchanged (probed one by one);
- `Bnd_Box.Get()` gained an overload returning a struct the bindings never
  register, and pybind11 tries it first, so EVERY call raises `Unable to
  convert function return value` in 8.0. `CornerMin()` / `CornerMax()` give
  the same six doubles in both (gap included, as `Get()` did), and raise the
  same `Standard_ConstructionError` on a void box; `box_limits` below is the
  one way a box is read now.

The trap inside the rename: 8.0 binds TWO of each shape map, and they are not
interchangeable. `IndexedMap_TopoDS_Shape` keys on `IsEqual`, which counts
orientation; `..._TopTools_ShapeMapHasher` keys on `IsSame`, which does not.
7.9's `TopTools_*` maps are the hasher ones - measured on a cube, whose 12
edges come back as 12 under the hasher and 24 under the default, because the
two faces sharing an edge see it with opposite orientations; and a face bound
in the hasher data map is found by its reversed twin, in the plain one it is
not. `fuse_keeping_faces` looks a face up that way, and `free_edges` counts
edges that way, so the plain maps would have been a silent, everywhere-wrong
answer.

Import from here, never from `OCP.TopTools` / `OCP.TDF` / `OCP.TColgp`, for
these names: `TopTools_ListOfShape`, `TopTools_HSequenceOfShape`,
`TopTools_DataMapOfShapeInteger`, `TopTools_IndexedMapOfShape`,
`TopTools_IndexedDataMapOfShapeListOfShape`, `TDF_LabelSequence`,
`TColgp_Array1OfPnt2d`. The window's side (`gui`, `settings`, `build`,
`defaults`, the worker's module level) imports nothing from here either - it
imports no OpenCASCADE at all (round 80, G5).
"""
from __future__ import annotations

import importlib.util
import sys

try:
    from OCP.TColgp import TColgp_Array1OfPnt2d
    from OCP.TDF import TDF_LabelSequence
    from OCP.TopTools import (TopTools_DataMapOfShapeInteger, TopTools_HSequenceOfShape,
                              TopTools_IndexedDataMapOfShapeListOfShape,
                              TopTools_IndexedMapOfShape, TopTools_ListOfShape)
except ImportError:
    try:
        from OCP.collections import (
            Array1_gp_Pnt2d as TColgp_Array1OfPnt2d,
            DataMap_TopoDS_Shape_int_TopTools_ShapeMapHasher as TopTools_DataMapOfShapeInteger,
            HSequence_TopoDS_Shape as TopTools_HSequenceOfShape,
            IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher
            as TopTools_IndexedDataMapOfShapeListOfShape,
            IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape,
            List_TopoDS_Shape as TopTools_ListOfShape,
            Sequence_TDF_Label as TDF_LabelSequence)
    except ImportError as exc:  # pragma: no cover - environment problem, not logic
        # An installed OCP that binds a name differently is not "OCP is
        # missing"; say which OCP this is and which ones the code knows, so
        # the report arrives with the symbol's name rather than "it does not
        # work with a newer cadquery".
        if importlib.util.find_spec("OCP") is None:
            raise SystemExit(
                f"{exc}\n\nSimple 3D needs OCP, the OpenCASCADE bindings, and the "
                f"Python running this does not have it:\n  {sys.executable}\n\n"
                f"Either install it there:\n  pip install \"cadquery-ocp>=7.7,<9\"\n"
                f"or start this with the Python that already has it.") from exc
        import OCP as _ocp
        raise SystemExit(
            f"{exc}\n\nOCP {getattr(_ocp, '__version__', '(version unknown)')} is "
            f"installed in\n  {sys.executable}\nbut does not bind a name Simple 3D "
            f"uses. This Simple 3D knows the bindings of OCCT 7.7 to 8.0 "
            f"(cadquery-ocp 7.7 - 8.0.1); a newer one may have renamed it again. "
            f"Try:\n  pip install \"cadquery-ocp>=7.7,<9\"") from exc


def box_limits(box) -> tuple[float, float, float, float, float, float]:
    """(xmin, ymin, zmin, xmax, ymax, zmax) of a Bnd_Box - what `Get()` gave in
    7.9 and cannot give in 8.0. Raises Standard_ConstructionError on a void
    box, as `Get()` did; callers that may see one ask `IsVoid()` first."""
    lo, hi = box.CornerMin(), box.CornerMax()
    return lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()


__all__ = [
    "TColgp_Array1OfPnt2d", "TDF_LabelSequence", "TopTools_DataMapOfShapeInteger",
    "TopTools_HSequenceOfShape", "TopTools_IndexedDataMapOfShapeListOfShape",
    "TopTools_IndexedMapOfShape", "TopTools_ListOfShape", "box_limits",
]
