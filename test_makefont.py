"""
makefont tests

nosetests -d --with-coverage --cover-package=makefont
"""

from io import StringIO
from lxml import etree

from nose import with_setup
from shapely.geometry import box, Polygon, MultiPolygon

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
VLINE = lambda x, y1, y2: box(x, y1, x+1, y2)
DOT = lambda x, y: box(x, y, x+1, y+1)

BOXES_01 = [
    HLINE(1, 7, 2),

    DOT(2, 4),
    DOT(5, 4),

    VLINE(0, 3, 10),
    VLINE(7, 3, 10),
    HLINE(1, 7, 10),


    Polygon(((2, 7), (6, 7), (6, 8), (5, 8), (5, 9), (3, 9), (3, 8), (2, 8)))
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
def test_outline():
    outline = makefont.CharacterOutline(charset[1])
    actual = outline.geometry
    expected = MultiPolygon(BOXES_01)
    assert expected.equals(actual)


@with_setup(load_charset)
def test_charset_sequence():
    assert len(charset) == 256
    charset[255]


def test_valid_svg():
    with open('SVG.xsd') as xsd:
        schema = etree.XMLSchema(file=xsd)

    with open('default.chr', 'rb') as chr_file:
        svg = makefont.svg_for_chr(chr_file)

    doc = etree.parse(StringIO(svg))
    schema.assertValid(doc)
