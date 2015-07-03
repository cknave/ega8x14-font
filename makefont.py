#!/usr/bin/env python3

from collections import namedtuple

# Assume all characters are 8px wide
LAST_X = 7


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
            raise KeyError
        return Character(self, character)

    def pixel(self, character, x, y):
        assert 0 <= x <= LAST_X
        byte = self.data[character * self.character_height + y]
        return (byte >> (LAST_X - x)) & 1


class Character:
    def __init__(self, charset, character):
        self.charset = charset
        self.character = character

    width = property(lambda _: LAST_X + 1)
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
                rectangles.append(Rectangle(rect_start, y, x, y+1))
                rect_start = None
    return rectangles
