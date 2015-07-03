"""
makefont tests

nosetests -d --with-coverage --cover-package=makefont
"""

from io import StringIO
from lxml import etree

from nose import with_setup

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

LINE = lambda x1, x2, y: makefont.Rectangle(x1, y, x2, y+1)
DOT = lambda x, y: makefont.Rectangle(x, y, x+1, y+1)
RECTANGLES_01 = [
    LINE(1, 7, 2),

    DOT(0, 3),
    DOT(7, 3),

    DOT(0, 4),
    DOT(2, 4),
    DOT(5, 4),
    DOT(7, 4),

    DOT(0, 5),
    DOT(7, 5),

    DOT(0, 6),
    DOT(7, 6),

    DOT(0, 7),
    LINE(2, 6, 7),
    DOT(7, 7),

    DOT(0, 8),
    LINE(3, 5, 8),
    DOT(7, 8),

    DOT(0, 9),
    DOT(7, 9),

    LINE(1, 7, 10)
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
    rects = makefont.rectangles(charset[1])
    assert rects == RECTANGLES_01


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
