"""The board's two outer faces at a point - where a part stands and a pad,
its mask window and a drawn opening lie (round 103).

A zone's stackup says how thick its stack can be; what is there at a point is
the layers that have material there. A positive layer (stiffener, adhesive)
is its drawn shapes, a negative one (coverlay, mask) the zone less its
openings, a layer without shapes the whole zone - `board._layer_region`, the
same function the body is built from. So the top of the board at (x, y) is
the top of the highest layer with material there, in any zone whose contour
holds the point (the zones of a real board overlap: flex-b2 53.6 mm2), and the
bottom likewise; the board's cutouts are not taken out, so a pin over its own
drill hole is given the face around the hole.

Measured before this round (the 23.10.2026 review, R3-1 and R4-2): every
height was the zone's whole stack. X1 on flex2-a0 stood 0.575 mm above the
board under it, in a window of the stiffener; flex-b2's connector pads lay
0.150-2.033 mm above it, over the stiffener's holes; flex3-a0's bottom pads
0.052 mm below their coverlay's openings.
"""

from __future__ import annotations

from .contour import contour_points
from .reporting import LogFn, _noop_log

# How far outside a face's box a point may lie and still be asked about.
BOX_GAP = 1e-6          # mm


class Surface:
    """`at(x, y)`: (top, bottom) of the material at a flat point, or None
    where no zone holds it. A layer's region is worked out the first time a
    point of its zone asks, then kept."""

    def __init__(self, zones: list[dict] | None, stackups: dict | None, shift: float,
                 log: LogFn = _noop_log) -> None:
        self.log = log
        self.zones = []
        for zone in zones or []:
            stackup = (stackups or {}).get(str(zone.get("stackup")))
            contour = zone.get("contour") or []
            polygon = contour_points(contour)
            if not stackup or not polygon:
                continue
            layers = []
            for layer in stackup.get("layers") or []:
                top = float(layer["z_top"]) + shift
                bottom = float(layer["z_bottom"]) + shift
                if top > bottom:                    # as layer_solids builds them
                    layers.append((layer, top, bottom))
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            self.zones.append((str(zone.get("name")), polygon, contour, layers,
                               (min(xs) - BOX_GAP, min(ys) - BOX_GAP, max(xs) + BOX_GAP, max(ys) + BOX_GAP)))
        self._regions: dict[tuple[int, int], list] = {}
        self._zone_faces: dict[int, object] = {}

    def __bool__(self) -> bool:
        return bool(self.zones)

    def _faces(self, zone_index: int, layer_index: int) -> list:
        """The layer's material in its zone as (face, box) pairs at z = 0."""
        key = (zone_index, layer_index)
        if key not in self._regions:
            from OCP.Bnd import Bnd_Box
            from OCP.BRepBndLib import BRepBndLib
            from OCP.TopAbs import TopAbs_FACE
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopoDS import TopoDS

            from .board import _layer_region

            _name, _polygon, contour, layers, _box = self.zones[zone_index]
            region = _layer_region(layers[layer_index][0], contour, 0.0, self.log)
            faces = []
            if region is not None:
                exp = TopExp_Explorer(region, TopAbs_FACE)
                while exp.More():
                    face = TopoDS.Face_s(exp.Current())
                    box = Bnd_Box()
                    BRepBndLib.Add_s(face, box)
                    faces.append((face, box))
                    exp.Next()
            self._regions[key] = faces
        return self._regions[key]

    def _in_zone(self, zone_index: int, x: float, y: float) -> bool:
        """Is the point on the zone's own face - its contour as the body
        builds it, arcs and all, not a polygon sampled from it?"""
        if zone_index not in self._zone_faces:
            from .contour import _face_from_wires, build_contour

            self._zone_faces[zone_index] = _face_from_wires(
                build_contour(self.zones[zone_index][2], 0.0), [])
        return _on_face(self._zone_faces[zone_index], x, y)

    def _holds(self, zone_index: int, layer_index: int, x: float, y: float) -> bool:
        layer = self.zones[zone_index][3][layer_index][0]
        if not layer.get("shapes"):
            return True                             # the whole zone
        from OCP.gp import gp_Pnt

        point = gp_Pnt(x, y, 0.0)
        return any(not box.IsOut(point) and _on_face(face, x, y)
                   for face, box in self._faces(zone_index, layer_index))

    def at(self, x: float, y: float) -> tuple[float, float] | None:
        tops, bottoms = [], []
        for zi, (_name, polygon, _contour, layers, (x0, y0, x1, y1)) in enumerate(self.zones):
            if not (x0 <= x <= x1 and y0 <= y <= y1) or not self._in_zone(zi, x, y):
                continue
            for li, (_layer, top, bottom) in enumerate(layers):
                if self._holds(zi, li, x, y):
                    tops.append(top)
                    bottoms.append(bottom)
        return (max(tops), min(bottoms)) if tops else None


def _on_face(face, x: float, y: float) -> bool:
    """A flat point inside a planar face at z = 0, or on its edge."""
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON
    from OCP.gp import gp_Pnt

    return BRepClass_FaceClassifier(face, gp_Pnt(x, y, 0.0), BOX_GAP).State() in (TopAbs_IN, TopAbs_ON)
