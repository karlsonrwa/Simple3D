"""
Board colour themes.

The eight soldermask colours are lifted verbatim from Allegro's
`Allegro3DCanvasPreferences.xml` (the FixedThemes / soldermask entries) and
hardcoded here, so the tool needs neither the XML at runtime nor a parser.
Transparency is intentionally dropped: the board is one opaque solid, so only
the RGB triple is kept.

Values are 0-255 sRGB, matching how Allegro stores them. `as_fraction` converts
to the 0..1 the STEP writer wants.
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

# Typical FR4 dielectric, for the "cream" rim option. Not a mask colour, so it
# is kept separate from the themes above.
CREAM_DIELECTRIC = (253, 255, 215)

# Silkscreen ink. Real legend ink comes in exactly these two in practice, so
# this is a closed choice rather than a free colour: white on dark masks, black
# on white/yellow ones. Neither is a pure 255/0 - printed ink never is, and a
# pure white next to a pure white mask disappears.
SILK_COLORS: dict[str, tuple[int, int, int]] = {
    "White": (242, 242, 242),
    "Black": (26, 26, 26),
}

SILK_ORDER = ["White", "Black"]

DEFAULT_SILK = "White"


def resolve_silk_color(name: str) -> tuple[int, int, int]:
    """'White'/'Black' (or a custom 'r,g,b' / '#rrggbb') -> RGB 0-255."""
    if name in SILK_COLORS:
        return SILK_COLORS[name]
    return parse_hex(name)


def as_fraction(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """0-255 sRGB triple -> 0..1 triple for the STEP writer."""
    r, g, b = rgb
    return (r / 255.0, g / 255.0, b / 255.0)


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
        raise ValueError(f"Expected a 6-digit hex colour, got {text!r}")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


# --------------------------------------------------------------------------- #
# stackup layer kinds, for the layer-coloured board
# --------------------------------------------------------------------------- #

# The kinds a flex / rigid-flex stackup is made of, in the order the swatch row
# shows them. Defaults are Allegro's OWN material colours, read off a real
# board's 3DX_APPEARANCE attachment - so a layer-coloured export looks like the
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
    for marker, kind in (("SOLDERMASK", "soldermask"), ("COVERLAY", "coverlay"),
                         ("ADHESIVE", "adhesive"), ("STIFFENER", "stiffener")):
        if marker in probe:
            return kind
    return "other"


def resolve_board_color(theme: str) -> tuple[int, int, int]:
    """Theme name or a custom 'r,g,b' / '#rrggbb' string -> RGB 0-255."""
    if theme in BOARD_THEMES:
        return BOARD_THEMES[theme]
    return parse_hex(theme)
