import argparse
import os
# import sys
import warnings
import json
import math

from OCC.Core.STEPControl import STEPControl_Reader, STEPControl_Writer, STEPControl_AsIs
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.gp import gp_Trsf, gp_Vec, gp_Ax1, gp_Ax2, gp_Pnt, gp_Circ, gp_Dir 
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
from OCC.Core.GC import GC_MakeArcOfCircle
from OCC.Core.TopoDS import TopoDS_Compound
from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCC.Core.TopLoc import TopLoc_Location

def buildContour(contour):
    """Make a wire."""
    edges = []

    # make board contour
    for segment in contour:

        if segment['type']=='arc':
            #  get radius and coordinates from json
            radius = segment['radius']
            p_center = gp_Pnt(segment['center'][0],
                              segment['center'][1], 0)

            # build arc from circle
            circle = gp_Circ(gp_Ax2(p_center,
                                    gp_Dir(0, 0, 1)),
                                    radius)
            arc = GC_MakeArcOfCircle(circle,
                                     math.radians( segment['beta'] ),
                                     math.radians( segment['alpha'] ),
                                     segment['ccw']).Value()

            # append edges
            edges.append(BRepBuilderAPI_MakeEdge(arc).Edge())

        elif segment['type']=='circle':
            #  get radius and coordinates from json
            radius = segment['radius']
            xy = gp_Pnt(segment['x'],
                        segment['y'], 0)

            # build circle
            circle = gp_Circ(gp_Ax2(xy,
                                    gp_Dir(0, 0, 1)),
                                    radius)

            # append edges
            edges.append(BRepBuilderAPI_MakeEdge(circle).Edge())
        else:
            # get start and end points
            p_start = gp_Pnt(segment['start'][0],
                             segment['start'][1],
                             0)
            
            p_end = gp_Pnt(segment['end'][0],
                           segment['end'][1],
                           0)

            # append edges
            edges.append(BRepBuilderAPI_MakeEdge(p_start,p_end).Edge())

    # create wire maker
    wire_maker = BRepBuilderAPI_MakeWire()

    # add edges to wire maker
    for e in edges:
        wire_maker.Add(e)
    
    if not wire_maker.IsDone():
        raise AssertionError("Wire not done.")

    # return wire
    return wire_maker.Wire()


def make_board_geometry(pcb):
    """Make the board geometry."""

    contours = pcb['edges']

    if( len(contours) == 1):
        outline = contours
    else:
        outline = contours[0]

    # make board contour
    wire = buildContour( outline )

    # make face
    face = BRepBuilderAPI_MakeFace(wire)

    # make cutouts/holes
    if( len(contours) > 1 ):
        cutouts = contours[1:]

        for cutout in cutouts:
            face.Add(buildContour(cutout))

    # make
    face = face.Face()

    # extrusion
    vec = gp_Vec(0, 0, - pcb['thickness'])
    return BRepPrimAPI_MakePrism(face, vec).Shape()

def findFile(name, path):
    """Find the given file."""

    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)
        
    return None

def load_step_file(filename):
    """Load a STEP file and return the shape."""
    
    reader = STEPControl_Reader()
    status = reader.ReadFile(filename)

    if status != IFSelect_RetDone:
        raise IOError(f"Error: Cannot read STEP file '{filename}'")
    
    reader.TransferRoots()

    return reader.OneShape()

def transform_shape(shape, translation=(0, 0, 0), rotation_x=0, rotation_y=0, rotation_z=0):
    """Apply translation and rotation to the passed shape."""

    # every transformation has to be done individually
    # transformations cannot be combined

    trsf = gp_Trsf()

    # apply x-rotation
    if rotation_x != 0:

        axis = gp_Ax1(gp_Pnt(0, 0, 0),
                      gp_Dir(*(1, 0, 0)))
        
        trsf.SetRotation(axis,
                         math.radians(rotation_x))

        transformer = BRepBuilderAPI_Transform(shape, trsf, True)
        shape = transformer.Shape()

    # apply y-rotation
    if rotation_y != 0:
        
        axis = gp_Ax1(gp_Pnt(0, 0, 0),
                      gp_Dir(*(0, 1, 0)))
        
        trsf.SetRotation(axis,
                         math.radians(rotation_y))

        transformer = BRepBuilderAPI_Transform(shape, trsf, True)
        shape = transformer.Shape()

    # apply z-rotation
    if rotation_z != 0:

        axis = gp_Ax1(gp_Pnt(0, 0, 0),
                      gp_Dir(*(0, 0, 1)))
        trsf.SetRotation(axis, math.radians(rotation_z))

        transformer = BRepBuilderAPI_Transform(shape, trsf, True)
        shape = transformer.Shape()

    # apply translation
    trsf.SetTranslation(gp_Vec(*translation))

    transformer = BRepBuilderAPI_Transform(shape, trsf, True)
    return transformer.Shape()

def merge_shapes(shapes):
    """Merge multiple shapes into a single compound."""

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)

    for shape in shapes:
        builder.Add(compound, shape)

    return compound

def save_step_file(shape, filename):
    """Save a shape to a STEP file."""

    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)

    status = writer.Write(filename)

    if status != IFSelect_RetDone:
        raise IOError(f"Error: Cannot write STEP file '{filename}'")

def main():
    parser = argparse.ArgumentParser(
        description='Process some integers.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument('file',
                        type=str,
                        help="Intermediate JSON file")
    
    parser.add_argument('step_dir',
                        type=str,
                        help="Path to step file directory")
    
    parser.add_argument('--filename',
                        type=str,
                        default=None,
                        help="Optional output filename"
                        )
    
    parser.add_argument('--pad-to-pad',
                        action='store_true',
                        help="PCB thickness without soldermask"
                        )
    
    args = parser.parse_args()

    # set 
    file = args.file
    step_dir = args.step_dir

    if args.filename is None:
        output_file = file.removesuffix(".json") + ".step"
    else:
        output_file = args.filename

    shapes = []
    cache = {}

    try:
        with open(file) as content:
            # load json file
            data = json.load(content)

            # create board geometry
            board_geometry = make_board_geometry(data['pcb'])
            shapes.append(board_geometry)

            for ref in data:
                # skip pcb geometry
                if ref=='pcb':
                    continue

                # status
                print(f"Adding '{ref}'")

                # get name of step file
                step_name = data[ref]['step_mapping']['step_name']

                # find step file
                step_file_path = findFile(step_name, step_dir )

                if step_file_path is None:
                    warnings.warn(f"Step model {step_name} not found.")
                    continue

                # check, if step file was previously loaded
                if step_name not in cache:
                    # load step file
                    shape = load_step_file(step_file_path)

                    # get step mapping data
                    step_mapping = data[ref]['step_mapping']
                    offset = (step_mapping['offset_x'],
                              step_mapping['offset_y'],
                              step_mapping['offset_z'])

                    # map the step file to the symbol origin
                    package = transform_shape(shape,
                                              translation=offset,
                                              rotation_x=step_mapping['rotation_x'],
                                              rotation_y=step_mapping['rotation_y'],
                                              rotation_z=step_mapping['rotation_z'])

                    cache[step_name] = package

                # shift the packge to symbol position
                if data[ref]['is_mirrored']:
                    rotation_x = -180.0
                    z = - data['pcb']['thickness']
                else:
                    rotation_x = 0.0
                    z = 0.0

                # make translation
                trsf = gp_Trsf()
                trsf.SetTranslation(gp_Vec(data[ref]['x'],
                                           data[ref]['y'],
                                           z))

                # flip component
                rx = gp_Trsf()
                rx.SetRotation(gp_Ax1(gp_Pnt(0,0,0),
                                      gp_Dir(1,0,0)),
                                      math.radians(rotation_x))
                
                trsf.Multiply(rx)

                # rotate
                rz = gp_Trsf()
                rz.SetRotation(gp_Ax1(gp_Pnt(0,0,0),
                                      gp_Dir(0,0,1)),
                                      math.radians(data[ref]['angle']))
                
                trsf.Multiply(rz)

                # map to step file
                loc = TopLoc_Location(trsf)
                instanced_shape = cache[step_name].Located(loc)

                #  append shape
                shapes.append(instanced_shape)

            # merge all shapes into one and create step file
            merged_shape = merge_shapes(shapes)
            save_step_file(merged_shape, output_file)

        print(f"The STEP file was saved as '{output_file}'")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()