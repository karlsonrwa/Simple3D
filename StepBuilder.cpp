#include <vector>
#include <cmath>
#include <gp_Pnt.hxx>
#include <gp_Dir.hxx>
#include <gp_Ax2.hxx>
#include <gp_Circ.hxx>
#include <GC_MakeArcOfCircle.hxx>
#include <BRepBuilderAPI_MakeEdge.hxx>
#include <BRepBuilderAPI_MakeWire.hxx>
#include <BRepBuilderAPI_MakeFace.hxx>
#include <BRepPrimAPI_MakePrism.hxx>
#include <BRepBuilderAPI_Transform.hxx>
#include <BRepAlgoAPI_Cut.hxx>
#include <gp_Vec.hxx>
#include <STEPCAFControl_Reader.hxx>
#include <STEPCAFControl_Writer.hxx>
#include <XCAFApp_Application.hxx>
#include <XCAFDoc_DocumentTool.hxx>
#include <XCAFDoc_ShapeTool.hxx>
#include <XCAFDoc_ColorTool.hxx>
#include <TDF_Label.hxx>
#include <TDocStd_Document.hxx>
#include <Quantity_Color.hxx>
#include <TDataStd_Name.hxx>
#include <iostream>
#include <fstream>
#include <string>
#include "json.hpp"
#include <filesystem>

using json = nlohmann::json;

TopoDS_Wire buildContour(const json& contour, double z_offset)
{
    std::vector<TopoDS_Edge> edges;

    for (const auto& segment : contour)
    {
        std::string type = segment["type"];

        if (type == "arc")
        {
            double radius = segment["radius"];

            gp_Pnt p_center(
                segment["center"][0],
                segment["center"][1],
                z_offset
            );

            gp_Circ circle(
                gp_Ax2(p_center, gp_Dir(0, 0, 1)),
                radius
            );

            double alpha = segment["alpha"];
            double beta = segment["beta"];
            bool ccw = segment["ccw"];

            Handle(Geom_TrimmedCurve) arc =
                GC_MakeArcOfCircle(
                    circle,
                    alpha * M_PI / 180.0,
                    beta * M_PI / 180.0,
                    ccw
                ).Value();

            edges.push_back(BRepBuilderAPI_MakeEdge(arc).Edge());
        }
        else if (type == "circle")
        {
            double radius = segment["radius"];

            gp_Pnt xy(
                segment["x"],
                segment["y"],
                z_offset
            );

            gp_Circ circle(
                gp_Ax2(xy, gp_Dir(0, 0, 1)),
                radius
            );

            edges.push_back(BRepBuilderAPI_MakeEdge(circle).Edge());
        }
        else
        {
            gp_Pnt p_start(
                segment["start"][0],
                segment["start"][1],
                z_offset
            );

            gp_Pnt p_end(
                segment["end"][0],
                segment["end"][1],
                z_offset
            );

            edges.push_back(BRepBuilderAPI_MakeEdge(p_start, p_end).Edge());
        }
    }

    BRepBuilderAPI_MakeWire wire_maker;

    for (const auto& e : edges)
        wire_maker.Add(e);

    if (!wire_maker.IsDone())
    {
        std::cerr << "Wire not done!\n";
        throw std::runtime_error("Wire not done");
    }

    return wire_maker.Wire();
}

TopoDS_Shape make_board_geometry(const json& pcb, double thickness, double z_offset = 0.0)
{
    const json& contours = pcb["edges"];

    json outline;
    if (contours.size() == 1) {
        outline = contours;
    }
    else {
        outline = contours[0];
    }

    TopoDS_Wire wire = buildContour(outline, z_offset);

    TopoDS_Face face = BRepBuilderAPI_MakeFace(wire).Face();

    gp_Vec vec(0, 0, -thickness);
    TopoDS_Shape board = BRepPrimAPI_MakePrism(face, vec).Shape();

    if (contours.size() > 1) {
        for (size_t i = 1; i < contours.size(); ++i) {
            const json& cutout = contours[i];

            TopoDS_Wire cut_wire = buildContour(cutout, z_offset);
            TopoDS_Face cut_face = BRepBuilderAPI_MakeFace(cut_wire).Face();
            TopoDS_Shape hole = BRepPrimAPI_MakePrism(cut_face, vec).Shape();

            board = BRepAlgoAPI_Cut(board, hole).Shape();
        }
    }

    return board;
}

std::string find_file(const std::string& name, const std::string& path)
{
    namespace fs = std::filesystem;

    for (const auto& entry : fs::recursive_directory_iterator(path)) {
        if (entry.is_regular_file() && entry.path().filename() == name) {
            return entry.path().string();
        }
    }

    return "";
}

struct step_mapping {
    TDF_Label label;
    json mapping;
};

int main(int argc, char* arg[])
{
    std::string step_dir = "test/step_files";
    std::string input_file = "test/test.json";
    std::string output_path = "test/output/";

    if (argc > 1) {
        // input args
        step_dir = arg[1];
        input_file = arg[2];
        output_path = arg[3];
    }

    if (!std::filesystem::exists(step_dir)) {
        std::cout << "Step files directory does not exist... press enter to quit.\n";
        std::cin.get();
        return -1;
    }

    if (!std::filesystem::exists(input_file)) {
        std::cout << "Input file does not exist... press enter to quit.\n";
        std::cin.get();
        return -1;
    }

    // read & parse json file
    std::cout << "read " << input_file << "\n";
    std::ifstream f(input_file);
    json data = json::parse(f);

    // check json
    if (!data.contains("name")) {
        std::cout << "Name is missing.\n";
        std::cin.get();
        return -1;
    }

    if (!data.contains("pcb") || !data["pcb"].contains("thickness") || !data["pcb"].contains("edges") || !data["pcb"].contains("color")) {
        std::cout << "PCB informations are missing.\n";
        std::cin.get();
        return -1;
    }

    // set pcb name
    std::string pcb_name = data["name"];

    // create xcaf
    Handle(XCAFApp_Application) app = XCAFApp_Application::GetApplication();
    Handle(TDocStd_Document) doc;
    app->NewDocument("MDTV-XCAF", doc);

    Handle(XCAFDoc_ShapeTool) shapeTool =
        XCAFDoc_DocumentTool::ShapeTool(doc->Main());

    Handle(XCAFDoc_ColorTool) colorTool =
        XCAFDoc_DocumentTool::ColorTool(doc->Main());

    // make main assembly
    TDF_Label mainAssembly = shapeTool->NewShape();
    TDataStd_Name::Set(mainAssembly, data["name"].get<std::string>().c_str());

    // create pcb
    // store pcb thickness
    double pcb_thickness = data["pcb"]["thickness"]["board"];

    TopoDS_Shape boardContour = make_board_geometry(data["pcb"], pcb_thickness, 0.0);
    TDF_Label pcb = shapeTool->NewShape();
    shapeTool->SetShape(pcb, boardContour);

    // definde colors
    double r = data["pcb"]["color"]["r"];
    double g = data["pcb"]["color"]["g"];
    double b = data["pcb"]["color"]["b"];

    //Quantity_Color pcbGreen(0.0, 0.4, 0.0, Quantity_TOC_RGB);
    Quantity_Color pcbColor(r, g, b, Quantity_TOC_RGB);

    colorTool->SetColor(pcb, pcbColor, XCAFDoc_ColorSurf);
    colorTool->SetColor(pcb, pcbColor, XCAFDoc_ColorCurv);
    colorTool->SetColor(pcb, pcbColor, XCAFDoc_ColorGen);

    TDataStd_Name::Set(pcb, "PCB");

    shapeTool->AddComponent(mainAssembly, pcb, TopLoc_Location(gp_Trsf()));

    // retain only components
    data.erase("name");
    data.erase("pcb");

    // cache
    std::unordered_map<std::string, step_mapping> cache;

    // import and place component
    for (auto& item : data.items()) {
        auto component = item.key();

        // find step file
        std::string step_name = data[component]["step_mapping"]["step_name"];

        // check, if step file is already contained in cache
        if (!cache.contains(step_name)) {
            std::string step_file_path = find_file(step_name, step_dir);

            if (step_file_path == "") {
                std::cout << "Could not find " << step_name << "\n";
                continue;
            }

            STEPCAFControl_Reader reader;
            reader.SetColorMode(true);

            std::cout << "Reading " << step_name << "\n";
            reader.ReadFile(step_file_path.c_str());
            reader.Transfer(doc);

            TDF_LabelSequence roots;
            shapeTool->GetFreeShapes(roots);

            cache[step_name].label = roots.Value(roots.Length());
            cache[step_name].mapping = data[component]["step_mapping"];
        }

        // map step model to component origin
        double rotation_x = double(cache[step_name].mapping["rotation_x"]);
        double rotation_y = double(cache[step_name].mapping["rotation_y"]);
        double rotation_z = double(cache[step_name].mapping["rotation_z"]);

        gp_Trsf rx = gp_Trsf();

        rx.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0),
            gp_Dir(1, 0, 0)),
            rotation_x * M_PI / 180.0);

        gp_Trsf ry = gp_Trsf();

        ry.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0),
            gp_Dir(0, 1, 0)),
            rotation_y * M_PI / 180.0);

        gp_Trsf rz = gp_Trsf();

        rz.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0),
            gp_Dir(0, 0, 1)),
            rotation_z * M_PI / 180.0);

        double offset_x = double(cache[step_name].mapping["offset_x"]);
        double offset_y = double(cache[step_name].mapping["offset_y"]);
        double offset_z = double(cache[step_name].mapping["offset_z"]);

        gp_Trsf offset = gp_Trsf();

        offset.SetTranslation(gp_Vec(
            offset_x,
            offset_y,
            offset_z
        ));

        // the order of the multiplication can not be changed
        gp_Trsf rotation = rz * ry * rx;

        // apply component angle
        gp_Trsf angle;

        angle.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0),
            gp_Dir(0, 0, 1)),
            double(data[component]["angle"]) * M_PI / 180.0
        );

        // apply mirroring
        double z = 0;

        gp_Trsf mirror;

        if (data[component]["is_mirrored"]) {
            z = -pcb_thickness;

            mirror.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), M_PI);
        }

        // set component position
        double x = double(data[component]["x"]);
        double y = double(data[component]["y"]);

        gp_Trsf position = gp_Trsf();

        position.SetTranslation(gp_Vec(
            x,
            y,
            z
        ));

        // create complete transformation
        // the transformation is not interchangeable and is applied from the right to the left
        gp_Trsf trsf = position * angle * mirror * offset * rotation;

        // create component instance
        TDataStd_Name::Set(cache[step_name].label, component.c_str());
        TDF_Label test = shapeTool->AddComponent(mainAssembly, cache[step_name].label, TopLoc_Location(trsf));
    }

    // update assembly
    // otherwise the document is empty
    shapeTool->UpdateAssemblies();

    STEPCAFControl_Writer writer;
    writer.SetColorMode(true);
    writer.SetNameMode(true);
    writer.Transfer(doc, STEPControl_AsIs);

    std::string file_name = output_path + "\\" + pcb_name + ".step";
    writer.Write(file_name.c_str());

    return 0;
}