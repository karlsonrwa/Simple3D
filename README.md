# STEP file generator for Allegro PCB Assembly Variants
**Skill script for Allegro PCB Designer to generate a JSON file containing the board contour and the STEP file mapping for each symbol, as well as the actual STEP file generation by a python script.**

## Prerequisites
To make the skill script available for use, you need to copy the `makeVariant3dIntermediates.il` file to your local skill directory ( usually your installation path + `\share\pcb\etc` ) or the skill directory in the `$CDS_SITE` path. Append it to the `allegro.ilinit` file ( add `load( "path/makeVariant3dIntermediates.il" )` ) or load it manually via the skill load command ( type `set telskill` into the command line and then type `load("makeVariant3dIntermediates.il" )`.

To run the python script, you need to install `python` and follow the installation instructions at [pythonocc-core](https://github.com/tpaviot/pythonocc-core).

## Usage
Once the script is loaded successfully, you can start exporting the json file by typing `skill makeVariant3dIntermediates( path ) + enter` in the command line.
A directory named like the passed argument is created in your project folder containing the `.json` files.

As a second step, the created `.json` file(s) need to be passed to the python script.
The python script accepts up to 4 arguments, where 2 are mandatory.

1. the filename or path to the `.json`` file
2. the path to the directory alle STEP files of your footprints are stored
3. (optional) filename of the output file (STEP), if not passed, the name will be the name of the `.json` file with the ending `.step`
4. (optional and not yet implemented) ignore the soldermask

### Example

`python makeStepFile.py "yourDesign.json" "path_to_you_step_files"`

## ToDos

- [ ] add support for mechanical holes
- [ ] add support for slot holes
- [ ] subtract the soldermask thickness from overall thickness