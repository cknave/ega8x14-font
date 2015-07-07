#!/usr/bin/env python3
"""Build the EGA 8x14 font."""

from itertools import combinations
import unicodedata
from xml.sax.saxutils import quoteattr

from shapely.affinity import scale
from shapely.geometry import box, LineString, Polygon, MultiPolygon
from shapely.ops import cascaded_union

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
        print("Outlining character {}".format(character.character))
        self.character = character
        boxes = self._scan_boxes(character)
        union = self._union_boxes(boxes, Polygon())
        overlapped = self._overlap_touching(union)
        self.geometry = self._simplify(overlapped)

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
            for x, pixel in enumerate(row + [0]):
                if pixel:
                    boxes.append(box(x, y, x+1, y+1))
        return boxes

    @classmethod
    def _union_boxes(cls, boxes, geometry):
        """Return a Polygon or MultiPolygon for all the boxes in the list.

        This method attempts to union all polygons first.  If that would cause a hole, the
        polygons will be combined into a MultiPolygon instead.

        :param list boxes: list of box polygons
        :param geometry: existing Polygon or MultiPolygon to combine with
        :return: a single Polygon or MultiPolygon containing all the boxes
        """
        combined = geometry
        while boxes:
            combined = cls._union_or_combine(boxes.pop(), combined)
        # Try to further union all combinations of polygons
        while isinstance(combined, MultiPolygon):
            geoms = list(combined.geoms)
            for poly1, poly2 in combinations(geoms, 2):
                if not poly1.touches(poly2):
                    continue
                union = poly1.union(poly2)
                if isinstance(union, Polygon) and not cls._has_holes(union):
                    new_geoms = list(geoms)
                    new_geoms.remove(poly1)
                    new_geoms.remove(poly2)
                    new_geoms.append(union)
                    combined = MultiPolygon(new_geoms)
                    break
            if len(geoms) == len(combined.geoms):
                # Tried all combinations, found no more unions
                break
        return combined

    @classmethod
    def _union_or_combine(cls, polygon, geometry):
        """Union or combine a Polygon into another Polygon or MultiPolygon.

        Unions will be attempted for all the polygons in geometry, only adding a new polygon
        if all attempts resulted in interior holes.
        """
        # Handle the simple polygon to polygon case.
        if isinstance(geometry, Polygon):
            union = geometry.union(polygon)
            if not cls._has_holes(union):
                return union
            return MultiPolygon([geometry, polygon])
        # Try to union with all the polygons in geometry first.
        geoms = list(geometry.geoms)  # GeometrySequence doesn't behave enough like a list
        for i, geom in enumerate(geoms):
            if not geom.touches(polygon):
                continue
            union = geom.union(polygon)
            if isinstance(union, Polygon) and not cls._has_holes(union):
                return MultiPolygon(geoms[:i] + [union] + geoms[i+1:])
        # No unions were possible!
        return MultiPolygon(geoms + [polygon])

    @classmethod
    def _has_holes(cls, geometry):
        """Check if a Polygon or MultiPolygon has any holes."""
        if isinstance(geometry, Polygon):
            return bool(geometry.interiors)
        for polygon in geometry:
            if polygon.interiors:
                return True
        return False

    @classmethod
    def _overlap_touching(cls, geometry):
        # Nothing to do for 0 or 1 polygons.
        if geometry.is_empty or isinstance(geometry, Polygon):
            return geometry
        # Everywhere a polygon touches another polygon, we need to extend its touching
        # segments inside the other.
        extensions = []
        for poly1, poly2 in combinations(geometry.geoms, 2):
            if not poly1.touches(poly2):
                continue
            for overlapper, overlapped in ((poly1, poly2), (poly2, poly1)):
                # Find all line segments in overlapper that touch overlapped.
                for i in range(len(overlapper.boundary.coords) - 1):
                    coords = overlapper.boundary.coords[i:i+2]
                    if not LineString(coords).touches(overlapped):
                        continue
                    extension = cls._find_overlap_box(coords, overlapped)
                    if extension:
                        extensions.append(extension)
                # Add extensions on to the overlapper polygon.
                if extensions:
                    new_overlapper = cascaded_union([overlapper] + extensions)
                    new_geoms = list(geometry.geoms)
                    overlapper_index = new_geoms.index(overlapper)
                    overlapped_index = new_geoms.index(overlapped)
                    print((overlapped_index, overlapper_index))
                    new_geoms[overlapper_index] = new_overlapper
                    # Overlapper should be drawn over top of overlapped
                    if overlapper_index < overlapped_index:
                        print(new_geoms)
                        new_geoms[overlapper_index] = overlapped
                        new_geoms[overlapped_index] = new_overlapper
                        print(new_geoms)
                    return cls._overlap_touching(MultiPolygon(new_geoms))
        # No overlaps left
        return geometry

    @classmethod
    def _find_overlap_box(cls, coords, overlapped):
        x1, x2 = coords[0][0], coords[1][0]
        y1, y2 = coords[0][1], coords[1][1]
        # Try to extrude a box from this segment into overlapped.
        if x1 < x2:  # Horizontal, facing down
            y2 += OVERLAP
        elif x2 < x1:  # Horizontal, facing up
            y1 -= OVERLAP
        elif y1 < y2:  # Vertical, facing left
            x1 -= OVERLAP
        elif y2 < y1:  # Vertical, facing right
            x2 += OVERLAP
        else:  # Same point, should never happen
            return None

        # Box coords must be sorted
        x1, x2 = sorted([x1, x2])
        y1, y2 = sorted([y1, y2])
        extruded = box(x1, y1, x2, y2)
        if overlapped.contains(extruded):
            return extruded
        else:
            return None

    @classmethod
    def _simplify(cls, geometry):
        """Simplify the geometry of a Polygon or MultiPolygons.

        This is done by replacing all geometries with their convex hull, which will have the
        minimum vertices required.  (We can do this because no geometries are allowed to have
        holes.
        """
        # Nope, can't use convex hull.  These shapes aren't convex just because they don't have
        # holes.
        return geometry
        # if geometry.is_empty:
        #     return geometry
        # if isinstance(geometry, Polygon):
        #     return geometry.boundary.convex_hull
        # if not isinstance(geometry, MultiPolygon):
        #     raise ValueError('Expected Polygon or MultiPolygon')
        # polygons = [cls._simplify(p) for p in geometry.geoms]
        # return MultiPolygon(polygons)

    def _svg_path_polygon(self, polygon):
        """Return the SVG path (M...Z) for a single polygon.

        All scaling for SVG is applied at this point.

        """
        if polygon.is_empty:
            return ""
        assert polygon.boundary.coords[0] == polygon.boundary.coords[-1]
        # Flip the y-axis because SVG.
        origin = (0, self.character.height)
        scaled = scale(polygon, SCALE, -SCALE, origin=origin)
        coords = ' '.join('{},{}'.format(int(x), int(y))
                          for x, y in scaled.boundary.coords)
        return 'M {} Z'.format(coords)


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
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" version="1.1">\n'
           '  <defs>\n'
           '    <font horiz-adv-x="{width}">\n'
           '      <font-face font-family="{font_name}" units-per-em="{width}"\n'
           '          cap-height="{height}" x-height="{height}" bbox="0 0 {width} {height}"/>\n'
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


if __name__ == '__main__':
    with open('default.chr', 'rb') as inpu7:
        data = inpu7.read()
        charset = Charset(data)
        outline_list = [CharacterOutline(c) for c in charset]
        svg = make_svg(charset, outline_list, 'cp437', 'EGA 8x14')
        with open('ega8x14.svg', 'wt') as output:
            output.write(svg)
