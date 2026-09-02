"""Folding one shape by a plan: cut it region by region, bend each strip,
put it back together.

`apply_plan` is FoldPlan.apply. A board is folded layer by layer and the
legend glyph by glyph, so this runs hundreds of times per build; the cheap
rejections in cut._cut_to_region are what make that affordable. Each strip
is built exactly where it can be (strip_revolve), wrapped where it cannot
(strip_wrap), and faceted as the last resort.
"""

from __future__ import annotations

from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.TopTools import TopTools_ListOfShape
from OCP.TopoDS import TopoDS_Compound, TopoDS_Iterator, TopoDS_Shape

from .constants import LogFn, _noop_log
from .cut import _cut_to_region
from .regions import _bbox, _is_empty
from .strip_revolve import _revolve_strip
from .strip_wrap import _map_strip


def apply_plan(plan, shape: TopoDS_Shape, fuse: bool = True,
               note: bool = True, log: LogFn = _noop_log) -> TopoDS_Shape:
    """Fold one shape: cut it region by region, bend, put back together.

    `fuse=False` returns a compound instead - right for the silkscreen,
    where the pieces were never one solid to begin with and fusing thousands
    of barely touching prisms was measured at 154% of the file size.
    """
    if shape is None or shape.IsNull() or not plan:
        return shape

    box = _bbox(shape)
    if box is None:
        return shape

    # A COMPOUND of many small independent solids - the printed legend,
    # thousands of glyphs and strokes - is folded one piece at a time.
    # Folded whole it is a boolean between a 45000-face compound and every
    # region in turn, and none of the cheap rejections can fire because the
    # compound's own bounding box covers the entire board. Piece by piece,
    # a glyph is a millimetre across: it lands in one region, is rejected by
    # every other on its bounding box, and needs no boolean at all unless it
    # straddles a bend. Only for fuse=False, which is what the legend uses -
    # a board body is one solid and has nothing to gain here.
    if not fuse:
        children = []
        it = TopoDS_Iterator(shape)
        while it.More():
            children.append(it.Value())
            it.Next()
        if len(children) > 1:
            out = []
            for child in children:
                done = apply_plan(plan, child, fuse=False, note=False, log=log)
                if done is not None and not _is_empty(done):
                    out.append(done)
            if not out:
                log("warning: folding cut the shape away entirely; left flat")
                return shape
            builder = BRep_Builder()
            compound = TopoDS_Compound()
            builder.MakeCompound(compound)
            for piece in out:
                builder.Add(compound, piece)
            return compound

    pieces: list[TopoDS_Shape] = []
    for region in plan.regions:
        if region.kind != "panel":
            continue
        piece = _cut_to_region(shape, region.bounds, box, region)
        if piece is None:
            continue
        if region.moved:
            piece = BRepBuilderAPI_Transform(piece, region.trsf, True).Shape()
        pieces.append(piece)

    for strip in plan.strips:
        flat = _cut_to_region(shape, strip.bounds, box, strip)
        if flat is None:
            continue
        bent = _revolve_strip(flat, strip)
        how, why = "exact", []
        if bent is None:
            bent = _map_strip(flat, strip, why)
            how = "wrapped"
        if bent is None:
            if note:
                plan._note_build(strip.bend.name, "faceted", log,
                                 why[0] if why else "")
            for region in strip.facets:
                piece = _cut_to_region(shape, region.bounds, box, region)
                if piece is None:
                    continue
                pieces.append(
                    BRepBuilderAPI_Transform(piece, region.trsf, True).Shape())
        else:
            if note:
                plan._note_build(strip.bend.name, how, log)
            pieces.append(bent)

    if not pieces:
        log("warning: folding cut the shape away entirely; left flat")
        return shape
    if len(pieces) == 1:
        return pieces[0]
    if not fuse:
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        for piece in pieces:
            builder.Add(compound, piece)
        return compound

    fused = _fuse_all(pieces, log)
    # A fuse that hands back nothing is how a whole layer disappears without
    # a word: one degenerate sliver among the pieces, and 173 mm3 of a flex
    # arm's dielectric came back as a null shape. The pieces themselves are
    # sound - they were cut and bent one at a time - so keep them as a
    # compound rather than lose the part, and say what happened.
    if fused is None or _is_empty(fused):
        log(f"warning: the {len(pieces)} folded piece(s) of this shape "
            f"could not be fused into one solid; keeping them as separate "
            f"bodies so the material is not lost")
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        for piece in pieces:
            builder.Add(compound, piece)
        return compound
    return fused


def _fuse_all(pieces: list[TopoDS_Shape], log: LogFn) -> TopoDS_Shape:
    """Fuse in one multi-argument boolean, then merge what is coplanar.

    The same shape of call as the stackup fuse, and for the same reason: pairwise
    fusing is quadratic and this list is one panel plus a dozen slices per bend.
    The unify pass is what removes the seams left where the board was cut into
    regions - inside a panel those faces are coplanar and have no business
    surviving.
    """
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

    arguments = TopTools_ListOfShape()
    arguments.Append(pieces[0])
    tools = TopTools_ListOfShape()
    for piece in pieces[1:]:
        tools.Append(piece)

    op = BRepAlgoAPI_Fuse()
    op.SetArguments(arguments)
    op.SetTools(tools)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        log("warning: could not fuse the folded pieces; leaving them separate")
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        for piece in pieces:
            builder.Add(compound, piece)
        return compound

    fused = op.Shape()
    try:
        unify = ShapeUpgrade_UnifySameDomain(fused, True, True, False)
        unify.Build()
        merged = unify.Shape()
        if not merged.IsNull():
            fused = merged
    except Exception as exc:                       # never fatal - see _stackup_board
        log(f"warning: could not merge the folded board's coplanar faces ({exc})")
    return fused
