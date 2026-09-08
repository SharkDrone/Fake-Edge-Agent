#!/usr/bin/env python3
"""Lag noen testbilder i images/ slik at agenten har noe a sende.

Krever Pillow. Kjor: python tools/make_sample_images.py
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw

IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"
SIZE = (640, 480)


def make_image(index: int) -> Image.Image:
    """Sjoblatt bakgrunn med noen figurer, sa hvert bilde er synlig ulikt."""
    base = random.randint(40, 90)
    image = Image.new("RGB", SIZE, (base // 3, base // 2, base + 60))
    draw = ImageDraw.Draw(image)

    for _ in range(random.randint(3, 7)):
        x, y = random.randint(0, SIZE[0]), random.randint(0, SIZE[1])
        r = random.randint(20, 90)
        shade = random.randint(60, 200)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(shade // 2, shade, shade))

    draw.text((16, 16), f"sample frame {index:02d}", fill=(255, 255, 255))
    return image


def main() -> None:
    IMAGES_DIR.mkdir(exist_ok=True)
    for index in range(1, 6):
        target = IMAGES_DIR / f"sample_{index:02d}.jpg"
        make_image(index).save(target, quality=85)
        print(f"skrev {target}")


if __name__ == "__main__":
    main()
