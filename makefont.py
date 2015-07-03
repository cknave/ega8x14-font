#!/usr/bin/env python3

from collections import namedtuple
import unicodedata
from xml.sax.saxutils import quoteattr

# Assume all characters are 8px wide
WIDTH = 8
LAST_X = WIDTH-1

# Special case: python doesn't decode CP437 visible control characters
# From http://stackoverflow.com/a/14553297/180891
CP437_OVERRIDES = {
    0x01: "\u263A", 0x02: "\u263B", 0x03: "\u2665", 0x04: "\u2666",
    0x05: "\u2663", 0x06: "\u2660", 0x07: "\u2022", 0x08: "\u25D8",
    0x09: "\u25CB", 0x0a: "\u25D9", 0x0b: "\u2642", 0x0c: "\u2640",
    0x0d: "\u266A", 0x0e: "\u266B", 0x0f: "\u263C", 0x10: "\u25BA",
    0x11: "\u25C4", 0x12: "\u2195", 0x13: "\u203C", 0x14: "\u00B6",
    0x15: "\u00A7", 0x16: "\u25AC", 0x17: "\u21A8", 0x18: "\u2191",
    0x19: "\u2193", 0x1a: "\u2192", 0x1b: "\u2190", 0x1c: "\u221F",
    0x1d: "\u2194", 0x1e: "\u25B2", 0x1f: "\u25BC", 0x7f: "\u2302",
}

# Unicode categories to filter out
FILTER_CATEGORIES = ('Cc', 'Zs')


class Charset:
    def __init__(self, data, character_height=14):
        assert character_height > 0
        assert len(data) % character_height == 0
        self.data = data
        self.character_height = character_height

    def __len__(self):
        return len(self.data) // self.character_height

    def __getitem__(self, character):
        if character < 0 or character >= len(self):
            raise IndexError
        return Character(self, character)

    def pixel(self, character, x, y):
        assert 0 <= x <= LAST_X
        byte = self.data[character * self.character_height + y]
        return (byte >> (LAST_X - x)) & 1


class Character:
    def __init__(self, charset, character):
        self.charset = charset
        self.character = character

    width = property(lambda _: WIDTH)
    height = property(lambda self: self.charset.character_height)

    pixel = lambda self, x, y: self.charset.pixel(self.character, x, y)


Rectangle = namedtuple('Rectangle', 'x1 y1 x2 y2')


def rectangles(character):
    rectangles = []
    for y in range(character.height):
        row = [character.pixel(x, y) for x in range(0, character.width)]
        rect_start = None
        for x, pixel in enumerate(row + [0]):
            if pixel and rect_start is None:
                rect_start = x
            if not pixel and rect_start is not None:
                # Invert the y-axis because SVG
                yi = character.height - y
                rectangles.append(Rectangle(rect_start, yi, x, yi-1))
                rect_start = None
    return rectangles


def unicode_characters(codepage, total_characters=256):
    characters = [bytes([i]).decode(codepage) for i in range(total_characters)]
    if codepage == 'cp437':
        for index, override in CP437_OVERRIDES.items():
            characters[index] = override
    return characters


def rectangle_path(r):
    return 'M {x1},{y1} H {x2} V {y2} H {x1} Z'.format(**vars(r))


def make_svg(charset, rectangles_list, codepage, font_name):
    assert len(charset) == len(rectangles_list)
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" version="1.1">'
           '<defs>'
           '<font horiz-adv-x="{width}">'
           '<font-face font-family="{font_name}" units-per-em="{width}"'
           '  cap-height="{charset.character_height}"'
           '  x-height="{charset.character_height}"/>'
           '<missing-glyph d=""/>\n'.format(width=WIDTH, charset=charset, font_name=font_name)]

    unicode_list = unicode_characters(codepage, len(charset))
    printable_enumerated = [(i, c) for i, c in enumerate(unicode_list)
                            if unicodedata.category(c) not in FILTER_CATEGORIES]
    for i, char in printable_enumerated:
        paths = ' '.join(rectangle_path(r) for r in rectangles_list[i])
        quoted = quoteattr(char)
        svg.append('<glyph unicode={} d="{}"/>\n'.format(quoted, paths))

    svg.append('</font>'
               '</defs>'
               '</svg>\n')

    return ''.join(svg)


if __name__ == '__main__':
    with open('default.chr', 'rb') as inpu7:
        data = inpu7.read()
        charset = Charset(data)
        rectangles_list = [rectangles(c) for c in charset]
        svg = make_svg(charset, rectangles_list, 'cp437', 'EGA 8x14')
        with open('ega8x14.svg', 'wt') as output:
            output.write(svg)
