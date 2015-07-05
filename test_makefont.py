"""
makefont tests

nosetests -d --with-coverage --cover-package=makefont
"""

from io import StringIO
from lxml import etree

from nose import with_setup
from shapely.geometry import box, MultiPolygon

import makefont

CHAR_01 = [
    "        ",
    "        ",
    " ###### ",
    "#      #",
    "# #  # #",
    "#      #",
    "#      #",
    "# #### #",
    "#  ##  #",
    "#      #",
    " ###### ",
    "        ",
    "        ",
    "        "
]

HLINE = lambda x1, x2, y: box(x1, y, x2, y+1)
VLINE = lambda x, y1, y2: box(x, y1, x, y2)
DOT = lambda x, y: box(x, y, x+1, y-1)

BOXES_01 = [
    HLINE(1, 7, 2),
    VLINE(0, 3, 9),
    VLINE(7, 3, 9),
    HLINE(1, 7, 10),

    DOT(0, 3),
    DOT(7, 3),

    HLINE(2, 6, 7),
    HLINE(3, 5, 8),
]

charset = None


def load_charset():
    global charset
    with open('default.chr', 'rb') as charfile:
        data = charfile.read()
        charset = makefont.Charset(data)


@with_setup(load_charset)
def test_char_01():
    for y, row in enumerate(CHAR_01):
        for x, pixel in enumerate(row):
            expected = 1 if pixel != ' ' else 0
            assert expected == charset.pixel(1, x, y)


@with_setup(load_charset)
def test_character_view():
    INDEX = 1
    character = charset[INDEX]
    assert charset.character_height == character.height
    for y in range(character.height):
        for x in range(8):
            assert character.pixel(x, y) == charset.pixel(INDEX, x, y)


@with_setup(load_charset)
def test_rectangles():
    outline = makefont.CharacterOutline(charset[2])
    #outline = makefont.CharacterOutline(charset[1])
    expected = MultiPolygon(BOXES_01)
    assert expected.equals(outline.geometry)


@with_setup(load_charset)
def test_charset_sequence():
    assert len(charset) == 256
    charset[255]


@with_setup(load_charset)
def test_valid_svg():
    with open('SVG.xsd') as xsd:
        schema = etree.XMLSchema(file=xsd)

    rectangles_list = [makefont.rectangles(c) for c in charset]
    svg = makefont.make_svg(charset, rectangles_list, 'cp437', 'EGA 8x14')

    doc = etree.parse(StringIO(svg))
    schema.assertValid(doc)
