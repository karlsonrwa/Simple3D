"""The XCAF document a build is assembled in, and its writer.

`StepDocument` owns the application, the document, the shape and colour
tools and the root assembly label that everything is added under; `write`
transfers the document and writes the AP214 file, with the one writer
setting that halves the file (`write.surfacecurve.mode`) set where it has
to be set - after the writer is constructed, whose constructor resets it.
`_set_color` paints a label in all three of XCAF's colour slots, which is
what makes the colour survive every reader. Round 73, plan A7: the
set-up and the write block of `generate`, as a class.
"""

from __future__ import annotations

from pathlib import Path

from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.Interface import Interface_Static
from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_StepModelType
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool

from .errors import StepBuilderError
from .models import _sanitize


def _set_color(color_tool, label, rgb01, srgb: bool) -> None:
    color_type = (
        Quantity_TypeOfColor.Quantity_TOC_sRGB
        if srgb
        else Quantity_TypeOfColor.Quantity_TOC_RGB
    )
    color = Quantity_Color(rgb01[0], rgb01[1], rgb01[2], color_type)
    for target in (
        XCAFDoc_ColorType.XCAFDoc_ColorSurf,
        XCAFDoc_ColorType.XCAFDoc_ColorCurv,
        XCAFDoc_ColorType.XCAFDoc_ColorGen,
    ):
        color_tool.SetColor(label, color, target)


class StepDocument:
    """One assembly document: `doc`, `shape_tool`, `color_tool`, and `root`,
    the top-level assembly named after the board."""

    def __init__(self, name: str) -> None:
        app = XCAFApp_Application.GetApplication_s()
        self.doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
        app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), self.doc)
        self.shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(self.doc.Main())
        self.color_tool = XCAFDoc_DocumentTool.ColorTool_s(self.doc.Main())
        self.root = self.shape_tool.NewShape()
        self.set_name(self.root, name)

    def set_name(self, label, name: str) -> None:
        """Name a label, sanitised the way every name in the file is."""
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(_sanitize(name)))

    def set_color(self, label, rgb01, srgb: bool) -> None:
        _set_color(self.color_tool, label, rgb01, srgb)

    def write(self, path: str | Path, minimize_size: bool) -> None:
        """Write the assembly to *path* as AP214.

        The assemblies are updated first - without that the written document
        is empty. `write.surfacecurve.mode` is set HERE, after the writer is
        constructed: its constructor resets this global to 1, so setting it any
        earlier is undone. Mode 0 drops the p-curves on faces -> about half the
        file size, geometry identical (same volume and bbox, verified). Set
        explicitly both ways so the sticky global never leaks between
        successive builds in one process.
        """
        self.shape_tool.UpdateAssemblies()

        writer = STEPCAFControl_Writer()
        writer.SetColorMode(True)
        writer.SetNameMode(True)
        Interface_Static.SetIVal_s("write.surfacecurve.mode", 0 if minimize_size else 1)

        if not writer.Transfer(self.doc, STEPControl_StepModelType.STEPControl_AsIs):
            raise StepBuilderError("STEP writer transfer failed")
        status = writer.Write(str(path))
        if status != IFSelect_ReturnStatus.IFSelect_RetDone:
            raise StepBuilderError(f"Failed to write {path} (status {status})")
