"""The three default numbers the window shows before a config is read.

They used to live beside the code that uses them - `DEFAULT_FLAT_HEIGHT` in
legend.py, the two fold numbers in bend/constants.py - and the window imported
those modules for three floats, and with them OpenCASCADE (about 1.2 s of
start-up for nothing the window does). Round 80, plan G5: the numbers live
here, the modules that use them import them from here, and the window's side
(settings, gui, build, the worker's module level) imports no OCP at all;
test_gui [0b] holds that line.
"""

# Clearance in mm between the board face and a flat (surface) silkscreen, so
# the two do not flicker in a viewer. One micron: enough to separate the
# planes, too little to see.
DEFAULT_FLAT_HEIGHT = 0.001

# Degrees of arc per slice for a bend that has to be faceted - only reached
# when neither exact construction (revolve, wrap) fits. 7.5 degrees is 12
# slices per right angle.
DEFAULT_SLICE_ANGLE = 7.5

# Where the neutral axis sits in the stack, as a fraction of the thickness
# from the inner surface; 0.5 is the middle, which is what Allegro lays out
# at (k = 0 there means the same thing).
DEFAULT_NEUTRAL_FACTOR = 0.5
