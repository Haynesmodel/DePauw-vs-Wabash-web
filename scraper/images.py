"""
Generated images: the 1200x630 link-preview card and the home-screen and browser icons.

Everything is drawn with Pillow from the bundled Barlow Condensed font (SIL Open Font License, see
static/fonts/OFL.txt), never from whatever fonts the machine happens to have, so the same data gives the
same PNG on a laptop and on GitHub Actions. Original design only: gold and scarlet accents, no school
logos, wordmarks, seals or mascot art.

Determinism: the font layout engine is pinned to BASIC (Raqm is not on every platform's wheels), the
palette quantizing is deterministic, and no metadata is written into the PNG.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parent.parent / "static" / "fonts"
BOLD = FONTS / "BarlowCondensed-Bold.ttf"
MEDIUM = FONTS / "BarlowCondensed-Medium.ttf"

OG_SIZE = (1200, 630)
SITE_ADDRESS = "depauwvswabash.com"

BG = (17, 17, 17)
GOLD = (224, 176, 32)
SCARLET = (211, 51, 75)
SCARLET_TEXT = (255, 141, 155)
GOLD_BAR = (201, 151, 0)      # the same gold and scarlet as favicon.svg
SCARLET_BAR = (166, 25, 46)
TEXT = (241, 239, 232)
MUTED = (181, 177, 165)
BORDER = (58, 56, 50)
TIE = (138, 134, 122)


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.BASIC)


def to_png(img: Image.Image, colors: int | None = None) -> bytes:
    """PNG bytes with no metadata. Flat artwork with soft text edges stays small as a 64-color palette."""
    if colors:
        img = img.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, compress_level=9)
    return buf.getvalue()


def og_version(totals: dict, holder: str | None, label: str | None = None) -> str:
    """Short query-string value that changes exactly when the picture would, so chat apps refetch it
    instead of showing a cached old one. Built from the inputs, not the PNG bytes."""
    key = f"{totals['depauw_wins']}-{totals['wabash_wins']}-{totals['ties']}-{holder or ''}"
    if label:                                   # game day: the picture has a "Game day" / "Final" line
        key += f"-{label}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def fit(text: str, path: Path, size: int, max_width: int) -> ImageFont.FreeTypeFont:
    """The largest font up to `size` that keeps `text` within max_width."""
    f = font(path, size)
    while size > 12 and f.getlength(text) > max_width:
        size -= 2
        f = font(path, size)
    return f


def og_image(totals: dict, holder: str | None, label: str | None = None) -> bytes:
    """The link-preview card: the three all-time totals, the Monon Bell holder and the site address.
    On game day a small "Game day" or "Final" line (the `label`) sits at the right of the holder line."""
    w, h = OG_SIZE
    img = Image.new("RGB", OG_SIZE, BG)
    d = ImageDraw.Draw(img)
    margin = 72

    d.text((margin, 150), "DePauw vs. Wabash", font=fit("DePauw vs. Wabash", BOLD, 136, w - 2 * margin),
           fill=TEXT, anchor="ls")
    d.text((margin, 206), "All-time head-to-head records in men’s sports", font=font(MEDIUM, 42),
           fill=MUTED, anchor="ls")

    tiles = [("DePauw wins", totals["depauw_wins"], GOLD, GOLD),
             ("Wabash wins", totals["wabash_wins"], SCARLET, SCARLET_TEXT)]
    if totals["ties"]:
        tiles.append(("Ties", totals["ties"], TIE, MUTED))
    gap = 24
    tile_w = (w - 2 * margin - gap * (len(tiles) - 1)) // len(tiles)
    top, tile_h = 250, 210
    for i, (tile_label, n, accent, label_color) in enumerate(tiles):
        x = margin + i * (tile_w + gap)
        d.rounded_rectangle((x, top, x + tile_w, top + tile_h), radius=14, outline=BORDER, width=3)
        d.rectangle((x + 3, top, x + tile_w - 3, top + 11), fill=accent)
        d.text((x + 28, top + 70), tile_label, font=font(MEDIUM, 44), fill=label_color, anchor="ls")
        number = f"{n:,}"
        d.text((x + 28, top + 182), number, font=fit(number, BOLD, 128, tile_w - 56), fill=TEXT, anchor="ls")

    if holder:
        prefix = "Monon Bell holder: "
        pf = font(MEDIUM, 50)
        d.text((margin, 534), prefix, font=pf, fill=MUTED, anchor="ls")
        color = GOLD if holder == "DePauw" else SCARLET_TEXT
        d.text((margin + pf.getlength(prefix), 534), holder, font=font(BOLD, 50), fill=color, anchor="ls")

    if label:
        lf = font(BOLD, 46)
        text = label.upper()
        tw, pad = lf.getlength(text), 22
        right = w - margin
        d.rounded_rectangle((right - tw - 2 * pad, 487, right, 546), radius=10, fill=GOLD)
        d.text((right - pad, 534), text, font=lf, fill=BG, anchor="rs")

    d.text((margin, 590), "Unofficial fan site", font=font(MEDIUM, 32), fill=MUTED, anchor="ls")
    d.text((w - margin, 592), SITE_ADDRESS, font=font(BOLD, 42), fill=TEXT, anchor="rs")

    d.rectangle((0, h - 18, w // 2, h), fill=GOLD_BAR)
    d.rectangle((w // 2, h - 18, w, h), fill=SCARLET_BAR)
    return to_png(img, colors=48)


def alumni_og_version(values: list) -> str:
    """Query-string value for the alumni card: changes exactly when a figure drawn on it changes."""
    key = "alumni-" + "-".join(f"{name}:{figure}" for name, figure in values)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def alumni_og_image(values: list) -> bytes:
    """The alumni page's link-preview card: the endowment per student for each school, as [(school, "$543,000")]
    in the same fonts and colors as og_image(). No logos, and no overall alumni score."""
    w, h = OG_SIZE
    img = Image.new("RGB", OG_SIZE, BG)
    d = ImageDraw.Draw(img)
    margin = 72

    d.text((margin, 150), "DePauw vs. Wabash", font=fit("DePauw vs. Wabash", BOLD, 136, w - 2 * margin),
           fill=TEXT, anchor="ls")
    d.text((margin, 206), "Alumni and endowment", font=font(MEDIUM, 42), fill=MUTED, anchor="ls")

    accents = {"DePauw": (GOLD, GOLD), "Wabash": (SCARLET, SCARLET_TEXT)}
    gap = 24
    tile_w = (w - 2 * margin - gap * (len(values) - 1)) // len(values)
    top, tile_h = 250, 210
    for i, (name, figure) in enumerate(values):
        accent, label_color = accents[name]
        x = margin + i * (tile_w + gap)
        d.rounded_rectangle((x, top, x + tile_w, top + tile_h), radius=14, outline=BORDER, width=3)
        d.rectangle((x + 3, top, x + tile_w - 3, top + 11), fill=accent)
        d.text((x + 28, top + 70), name, font=font(MEDIUM, 44), fill=label_color, anchor="ls")
        d.text((x + 28, top + 182), figure, font=fit(figure, BOLD, 128, tile_w - 56), fill=TEXT, anchor="ls")

    caption = "Endowment per student · audited FY2025 endowment ÷ fall 2024 enrollment"
    d.text((margin, 534), caption, font=fit(caption, MEDIUM, 46, w - 2 * margin), fill=MUTED, anchor="ls")

    d.text((margin, 590), "Unofficial fan site", font=font(MEDIUM, 32), fill=MUTED, anchor="ls")
    d.text((w - margin, 592), SITE_ADDRESS, font=font(BOLD, 42), fill=TEXT, anchor="rs")

    d.rectangle((0, h - 18, w // 2, h), fill=GOLD_BAR)
    d.rectangle((w // 2, h - 18, w, h), fill=SCARLET_BAR)
    return to_png(img, colors=48)


def icon_image(size: int, *, maskable: bool = False) -> Image.Image:
    """The two-bar mark from favicon.svg on a dark square, full bleed (no transparency, no rounding: iOS
    and Android round it themselves). The maskable version keeps the bars well inside the central circle
    that every launcher mask keeps."""
    img = Image.new("RGB", (size, size), BG)
    d = ImageDraw.Draw(img)
    scale = 0.56 if maskable else 0.84       # share of the square the mark may use
    unit = size * scale / 20                 # the mark is 20 units wide in the SVG (x 6..26)
    ox = size * (1 - scale) / 2 - 6 * unit
    oy = size / 2 - 16 * unit                # SVG bars run y 8..24, centered on 16
    for x0, x1, color in ((6, 15, GOLD_BAR), (17, 26, SCARLET_BAR)):
        d.rectangle((round(ox + x0 * unit), round(oy + 8 * unit), round(ox + x1 * unit) - 1,
                     round(oy + 24 * unit) - 1), fill=color)
    return img


def icon_png(size: int, *, maskable: bool = False) -> bytes:
    return to_png(icon_image(size, maskable=maskable))
