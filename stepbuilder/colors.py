"""
Board color themes.

The eight soldermask colors are lifted verbatim from Allegro's
`Allegro3DCanvasPreferences.xml` (the FixedThemes / soldermask entries) and
hardcoded here, so the tool needs neither the XML at runtime nor a parser.
Transparency is intentionally dropped: the board is one opaque solid, so only
the RGB triple is kept.

Values are 0-255 sRGB, matching how Allegro stores them; the STEP writer
divides by 255 where it builds its Quantity_Color.
"""

from __future__ import annotations

# name -> (r, g, b) in 0..255 sRGB, from Allegro3DCanvasPreferences.xml
BOARD_THEMES: dict[str, tuple[int, int, int]] = {
    "Black": (0, 0, 0),
    "Blue": (37, 93, 171),
    "Dark_green": (26, 89, 36),
    "Green": (64, 216, 87),
    "Purple": (170, 0, 255),
    "Red": (207, 11, 31),
    "White": (255, 255, 255),
    "Yellow": (255, 170, 0),
}

# Allegro's ActiveTheme in the supplied preferences file.
DEFAULT_THEME = "Dark_green"

# The order the dropdown should present them in.
THEME_ORDER = [
    "Dark_green",
    "Green",
    "Blue",
    "Red",
    "Purple",
    "Yellow",
    "Black",
    "White",
]

# Typical FR4 dielectric, for the "cream" rim option. Not a mask color, so it
# is kept separate from the themes above.
CREAM_DIELECTRIC = (253, 255, 215)

# Silkscreen ink. Real legend ink comes in exactly these two in practice, so
# this is a closed choice rather than a free color: white on dark masks, black
# on white/yellow ones.
#
# White was 242 rather than 255 on the reasoning that printed ink is never pure
# and that pure white would vanish against a white mask. Changed to 255 after
# the user pointed out the obvious: 242 reads plainly GREY next to the window's
# white entry fields, and the swatch is meant to show what you will get. The
# 13-point difference never saved the white-on-white case anyway.
#
# Black stays off pure zero: a true 0,0,0 renders as a hole rather than a
# surface in several viewers, and nothing about it looks wrong in the swatch.
SILK_COLORS: dict[str, tuple[int, int, int]] = {
    "White": (255, 255, 255),
    "Black": (26, 26, 26),
}

SILK_ORDER = ["White", "Black"]

DEFAULT_SILK = "White"


def resolve_silk_color(name: str) -> tuple[int, int, int]:
    """'White'/'Black' (or a custom 'r,g,b' / '#rrggbb') -> RGB 0-255."""
    if name in SILK_COLORS:
        return SILK_COLORS[name]
    return parse_hex(name)


def parse_hex(text: str) -> tuple[int, int, int]:
    """'#40D857' or '40D857' or '64,216,87' -> (64, 216, 87)."""
    text = text.strip()
    if "," in text:
        parts = [int(p) for p in text.split(",")]
        if len(parts) != 3 or not all(0 <= p <= 255 for p in parts):
            raise ValueError(f"Expected three 0-255 values, got {text!r}")
        return (parts[0], parts[1], parts[2])
    text = text.lstrip("#")
    if len(text) != 6:
        raise ValueError(f"Expected a 6-digit hex color, got {text!r}")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


# --------------------------------------------------------------------------- #
# stackup layer kinds, for the layer-colored board
# --------------------------------------------------------------------------- #

# The kinds a flex / rigid-flex stackup is made of, in the order the swatch row
# shows them. Defaults are Allegro's OWN material colors, read off a real
# board's 3DX_APPEARANCE attachment - so a layer-colored export looks like the
# same board does in Allegro's 3D canvas rather than like an arbitrary palette.
LAYER_KINDS: list[tuple[str, str, tuple[int, int, int]]] = [
    ("copper",     "Copper",     (0xB8, 0x73, 0x33)),   # 3d_color_outer_conductor
    ("base",       "Base",       (0xFC, 0xFF, 0xD6)),   # 3d_color_dielectric
    ("coverlay",   "Coverlay",   (0xF2, 0x94, 0x40)),   # 3d_color_coverlay
    ("adhesive",   "Adhesive",   (0xC8, 0xC8, 0xC8)),   # no Allegro entry; grey
    ("stiffener",  "Stiffener",  (0x5A, 0x8C, 0x5A)),   # no Allegro entry; FR4 green
    ("soldermask", "Soldermask", (0x1A, 0x59, 0x24)),   # 3d_color_soldermask
    ("other",      "Other",      (0x96, 0x96, 0x96)),
]

DEFAULT_LAYER_COLORS: dict[str, tuple[int, int, int]] = {
    key: rgb for key, _, rgb in LAYER_KINDS
}


def layer_kind(layer: dict) -> str:
    """Which of LAYER_KINDS a stackup layer belongs to.

    Type first, name second: a conductor is a conductor whatever it is called,
    while everything outside the core is a MASK layer and can only be told apart
    by its name. Same normalisation as the soldermask test in core - strip
    everything but letters and digits - so SOLDER_MASK_TOP and "Solder Mask"
    both land in the same place.
    """
    kind_of_type = {"CONDUCTOR": "copper", "PLANE": "copper", "DIELECTRIC": "base"}
    by_type = kind_of_type.get(str(layer.get("type") or "").upper())
    if by_type:
        return by_type

    probe = f"{layer.get('name') or ''} {layer.get('function') or ''}".upper()
    probe = "".join(c for c in probe if c.isalnum())
    # Several spellings per kind, because these names are typed by a person into
    # the cross-section editor and Allegro does not police them. Cadence's own
    # demo board spells it STIFFNER, without the second E, and its epoxy layer
    # EXPOXY: both fell through to "other" and came out undifferentiated grey,
    # which is what a layer-colored board is meant to prevent. Matching is on a
    # substring of name + function with everything but letters and digits
    # stripped, so STIFFNER_INNER1 and "Stiffner" alike land in the same place.
    for markers, kind in ((("SOLDERMASK",), "soldermask"),
                          (("COVERLAY",), "coverlay"),
                          (("ADHESIVE",), "adhesive"),
                          (("STIFFENER", "STIFFNER", "STIFNER"), "stiffener"),
                          # An epoxy layer declares layerFunction ADHESIVE on
                          # every board seen so far and is caught above by that;
                          # this is for one that leaves the function blank, so
                          # it joins the adhesive rather than becoming "other".
                          (("EPOXY", "EXPOXY"), "adhesive")):
        if any(marker in probe for marker in markers):
            return kind
    return "other"


def resolve_board_color(theme: str) -> tuple[int, int, int]:
    """Theme name or a custom 'r,g,b' / '#rrggbb' string -> RGB 0-255."""
    if theme in BOARD_THEMES:
        return BOARD_THEMES[theme]
    return parse_hex(theme)
