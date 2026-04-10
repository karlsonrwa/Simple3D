# STEP file generator for Allegro PCB Assembly Variants
**Skill script for Allegro PCB Designer to generate a JSON file containing the board contour and the STEP file mapping for each symbol, as well as the actual STEP file generation by a c++ console application using [opencascade](https://dev.opencascade.org/) .**

## Prerequisites
To make the skill script available for use, you need to copy the `makeVariant3dIntermediates.il` file to your local skill directory ( usually your installation path + `\share\pcb\etc` ) or the skill directory in the `$CDS_SITE` path. Append it to the `allegro.ilinit` file ( add `load( "path/makeVariant3dIntermediates.il" )` ) or load it manually via the skill load command ( type `set telskill` into the command line and then type `load("makeVariant3dIntermediates.il" )`.

To run the console application, you must extract the contents `dlls.zip` into the same directory where the `StepBuilder.exe` is located.
```
├── bin
│ ├── StepBuilder.exe 
│ │── TKernel.dll
│ │── ...
│ │── TKXSBase.dll
```

## Usage
Once the script is loaded successfully, you can start exporting the json file by typing `skill makeVariant3dIntermediates( path ) + enter` in the command line. 
A directory named like the passed argument is created in your project folder containing the `.json` files. An optional argument containing the pcb color as a list can be passed to the function. For example, `list( 0.0 0.4 0.0 )`.

As a second step, the created `.json` file(s) need to be passed to the console application.
The application accepts 3 mandatory arguments.

1. the path to the directory all STEP files of your footprints are stored
2. the filename or full path to the `.json` file
3. the path to the directory the output file should be stored (the filename is defined by the `name` field in the `.json` file)

### Example

`StepBuilder.exe "path\to\your\step\files" "path\to\yourDesign.json" "path\to\output\file\directory"`

The application can be launched directly from Allegro using.

`shell( "StepBuilder.exe \"path\to\your\step\files" \"path\to\yourDesign.json\" \"path\to\output\file\directory"" )`.

Don't forget to escape all backslashes.