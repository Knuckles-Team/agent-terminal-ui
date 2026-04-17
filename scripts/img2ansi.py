#!/usr/bin/env python3
import sys
from PIL import Image

def image_to_ansi(image_path, width=40):
    try:
        img = Image.open(image_path)
    except Exception as e:
        print(f"Failed: {e}")
        return

    img = img.convert("RGBA")
    w, h = img.size
    aspect_ratio = h / w
    height = int(width * aspect_ratio * 0.5) # Terminal characters are ~twice as tall as wide
    img = img.resize((width, height), Image.Resampling.LANCZOS)

    out = []

    for y in range(height):
        for x in range(width):
            r, g, b, a = img.getpixel((x, y))
            if a < 128:
                out.append(" ")
            else:
                out.append(f"[#{r:02x}{g:02x}{b:02x}]█[/]")
        out.append("\n")

    print("".join(out))

if __name__ == "__main__":
    image_to_ansi(sys.argv[1])
