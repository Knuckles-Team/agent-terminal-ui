"""Literal terminal text filtering shared by public detail consumers."""


def display_text(value: str, *, multiline: bool = True) -> str:
    """Keep public text literal and strip terminal and directional controls."""
    return "".join(
        char
        for char in value
        if (
            (multiline and char in "\n\t")
            or (ord(char) >= 32 and not 127 <= ord(char) <= 159)
        )
        and char not in "\u061c\u200e\u200f"
        and not "\ud800" <= char <= "\udfff"
        and not "\u202a" <= char <= "\u202e"
        and not "\u2066" <= char <= "\u2069"
    )
