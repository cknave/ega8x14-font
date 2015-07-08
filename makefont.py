#!/usr/bin/env python3
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""Build the EGA 8x14 font."""

import unicodedata
from xml.sax.saxutils import quoteattr

from shapely.geometry import box, Polygon, MultiPolygon
from shapely.ops import cascaded_union

# Assume all characters are 8px wide
WIDTH = 8
LAST_X = WIDTH-1

# These metrics are correct for EGA 8x14
CAPITAL_HEIGHT = 12
LOWER_HEIGHT = 9
BASELINE = 4

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
FILTER_CATEGORIES = ('Cc')

# Pixels per em scale, since apparently 8 is too small
SCALE = 64

# Pixels to extend polygons into each other to prevent rendering gaps (pre-scaling)
OVERLAP = 0.25


class Charset:
    """Pixel data for a character set."""
    def __init__(self, data, character_height=14):
        """Initialize a Charset.

        :param bytes data: binary charset, one row per byte
        :param int character_height: number of rows per character
        """
        assert character_height > 0
        assert len(data) % character_height == 0
        self.data = data
        self.character_height = character_height

    def __len__(self):
        """Return the number of characters in the Charset."""
        return len(self.data) // self.character_height

    def __getitem__(self, character):
        """Get a single Character.

        :param int character: character index
        :returns: the Character
        :rtype: Character
        """
        if character < 0 or character >= len(self):
            raise IndexError
        return Character(self, character)

    def pixel(self, character, x, y):
        """Get a pixel value.

        :param int character: character index
        :param int x: x-coordinate
        :param int y: y-coordinate
        :returns: 0 for off, 1 for on
        :rtype: int
        """
        assert 0 <= x <= LAST_X
        byte = self.data[character * self.character_height + y]
        return (byte >> (LAST_X - x)) & 1


class Character:
    """Pixel data for a character."""
    def __init__(self, charset, character):
        """Initialize a Character view into a Charset.

        :param Charset charset: the Charset
        :param int character: index into charset
        """
        self.charset = charset
        self.character = character

    width = property(lambda _: WIDTH, doc="width of the character")
    height = property(lambda self: self.charset.character_height, doc="height of the character")

    def pixel(self, x, y):
        """Get a pixel value.

        :param int x: x-coordinate
        :param int y: y-coordinate
        :returns: 0 for off, 1 for on
        :rtype: int
        """
        return self.charset.pixel(self.character, x, y)


class CharacterOutline:
    """Outline paths for a character."""
    def __init__(self, character):
        """Initialize a CharacterOutline.

        :param Character character: character to use
        """
        self.character = character
        boxes = self._scan_boxes(character)
        union = cascaded_union(boxes)
        self.geometry = self._simplify(union)

    def svg_path(self):
        """Return the SVG path string for this outline."""
        if isinstance(self.geometry, Polygon):
            return self._svg_path_polygon(self.geometry)
        else:
            return ' '.join(self._svg_path_polygon(p) for p in self.geometry.geoms)

    @classmethod
    def _scan_boxes(cls, character):
        """Return a list of boxes from scanning the character left to right, top to bottom."""
        boxes = []
        for y in range(character.height):
            row = [character.pixel(x, y) for x in range(0, character.width)]
            box_start = None
            for x, pixel in enumerate(row + [0]):
                if pixel and box_start is None:
                    box_start = x
                if not pixel and box_start is not None:
                    boxes.append(box(box_start, y, x, y+1))
                    box_start = None
        return boxes

    @classmethod
    def _simplify(cls, geometry):
        """Simplify the geometry of a Polygon or MultiPolygons."""
        if geometry.is_empty:
            return geometry
        if isinstance(geometry, MultiPolygon):
            return MultiPolygon([cls._simplify_polygon(p) for p in geometry.geoms])
        else:
            return cls._simplify_polygon(geometry)

    @classmethod
    def _simplify_polygon(cls, polygon):
        exterior = cls._simplify_linear_ring(polygon.exterior)
        interiors = [cls._simplify_linear_ring(i) for i in polygon.interiors]
        return Polygon(exterior, interiors)

    @classmethod
    def _simplify_linear_ring(cls, ring):
        coords = list(ring.coords)
        # Drop vertices that are on the same line as both their neighbors.
        for i in range(len(coords)-2, 1, -1):
            a, b, c = coords[i-1:i+2]
            if a[0] == b[0] == c[0] or a[1] == a[1] == c[1]:
                del coords[i]
        return coords

    def _svg_path_polygon(self, polygon):
        """Return the SVG paths for a single polygon's exterior and interiors.

        All scaling for SVG is applied at this point.

        """
        paths = []
        # Draw the exterior clockwise (our geometry is CCW)
        paths.append(self._svg_path_coords(list(polygon.exterior.coords)[::-1]))
        # Draw the interiors counter-clockwise
        for interior in polygon.interiors:
            paths.append(self._svg_path_coords(list(interior.coords)[::-1]))
        return ' '.join(paths)

    def _svg_path_coords(self, coords):
        """Return the SVG path (M...Z) for a coordinate ring.

        """
        assert coords[0] == coords[-1]
        # origin = (0, self.character.height)
        paths = []
        for x, y in coords:
            x *= SCALE
            y = (y - self.character.height) * -SCALE
            paths.append('{},{}'.format(int(x), int(y)))
        return 'M {} Z'.format(' '.join(paths))


def unicode_characters(codepage, total_characters=256):
    """Return a list of the unicode characters for an encoding.

    :param str codepage: encoding name
    :param int total_characters: number of characters to return
    :returns: list of characters
    :rtype: list
    """
    characters = [bytes([i]).decode(codepage) for i in range(total_characters)]
    if codepage == 'cp437':
        for index, override in CP437_OVERRIDES.items():
            characters[index] = override
    return characters


def make_svg(charset, outline_list, codepage, font_name):
    assert len(charset) == len(outline_list)
    width = WIDTH * SCALE
    height = charset.character_height * SCALE
    cap_height = CAPITAL_HEIGHT * SCALE
    x_height = LOWER_HEIGHT * SCALE
    baseline = BASELINE * SCALE
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" version="1.1">\n'
           '  <defs>\n'
           '    <font horiz-adv-x="{width}">\n'
           '      <font-face font-family="{font_name}" units-per-em="{width}"\n'
           '          cap-height="{cap_height}" x-height="{x_height}" alphabetic="{baseline}"\n'
           '          bbox="0,0,{width},{height}" ascent="{height}" descent="0"/>\n'
           '      <missing-glyph d=""/>\n'.format(**locals())]

    unicode_list = unicode_characters(codepage, len(charset))
    filtered_enumerated = [(i, c) for i, c in enumerate(unicode_list)
                           if unicodedata.category(c) not in FILTER_CATEGORIES]
    for i, char in filtered_enumerated:
        paths = outline_list[i].svg_path()
        quoted_char = quoteattr(char)
        svg.append('<glyph unicode={} d="{}"/>\n'.format(quoted_char, paths))
        pass

    svg.append('    </font>\n'
               '  </defs>\n'
               '</svg>\n')

    return ''.join(svg)


def svg_for_chr(file):
    """Return SVG data for an input CHR file.

    :param file: file-like object containing binary CHR data
    :returns: SVG data
    """
    data = file.read()
    charset = Charset(data)
    outline_list = [CharacterOutline(c) for c in charset]
    return make_svg(charset, outline_list, 'cp437', 'EGA 8x14')


if __name__ == '__main__':
    with open('default.chr', 'rb') as chr_file:
        svg = svg_for_chr(chr_file)
        with open('ega8x14.svg', 'wt') as svg_file:
            svg_file.write(svg)
