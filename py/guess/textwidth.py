"""Approximate label sizes in GUESS units, for fitNodesToLabels.

Labels are drawn in Helvetica (or Arial, with the same widths) at 10 units
(40 px rendered at a quarter scale); these are Helvetica's AFM advance widths
for printable ASCII, in thousandths of the font size. Other characters use an
average width.
"""
FONT_SIZE = 10.0          # units, at labelsize 1 (renderer: fontSize 40 x LABEL_SCALE 0.25)
LINE_HEIGHT = 1.15        # line spacing, in font sizes

_WIDTHS = dict(zip(
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
    [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
     556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
     1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
     667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
     333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
     556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]))
_AVERAGE = 556


def line_width(text, scale=1.0):
    return sum(_WIDTHS.get(ch, _AVERAGE) for ch in text) / 1000 * FONT_SIZE * scale


def text_size(text, scale=1.0):
    """(width, height) of a label, honouring line breaks (\\n)."""
    lines = str(text).split("\n") or [""]
    return (max(line_width(line, scale) for line in lines),
            len(lines) * FONT_SIZE * LINE_HEIGHT * scale)
