"""Generate the brand images of the integration.

Home Assistant >= 2025.6 looks for the brand assets of a custom integration in
the ``brand`` folder of the integration.  Run this script from the repository
root to regenerate the images:

    python scripts/generate_brand_assets.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

BRAND_DIR = (
    Path(__file__).parent.parent
    / "custom_components"
    / "shelly_pro_3em_modbus"
    / "brand"
)

BACKGROUND = (20, 34, 61, 255)
CARD = (29, 52, 87, 255)
PHASE_COLORS = ((255, 205, 0, 255), (0, 173, 239, 255), (230, 87, 90, 255))

ICON_SIZES = (256, 512)
LOGO_SIZE = (512, 192)


def _draw_meter(size: int) -> Image.Image:
    """Draw the icon: a dark display with the traces of the three phases."""
    scale = size / 256
    image = Image.new("RGBA", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(image)

    margin = round(28 * scale)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=round(34 * scale),
        fill=CARD,
    )

    left = margin + round(22 * scale)
    width = size - 2 * left
    for index, color in enumerate(PHASE_COLORS):
        center = round((70 + 58 * index) * scale)
        points = [
            (
                left + round(width * step / 140),
                center + math.sin(step / 140 * 4 * math.pi) * 13 * scale,
            )
            for step in range(141)
        ]
        draw.line(points, fill=color, width=max(2, round(7 * scale)), joint="curve")

    return image


def _draw_logo(size: tuple[int, int]) -> Image.Image:
    """Draw the logo: the icon followed by one bar per phase."""
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.alpha_composite(_draw_meter(height), (0, 0))

    draw = ImageDraw.Draw(image)
    bar_left = height + round(height * 0.12)
    bar_width = width - bar_left - round(height * 0.12)
    for index, color in enumerate(PHASE_COLORS):
        top = round(height * (0.24 + 0.25 * index))
        draw.rounded_rectangle(
            (bar_left, top, bar_left + bar_width, top + round(height * 0.16)),
            radius=round(height * 0.08),
            fill=color,
        )
    return image


def main() -> None:
    """Write the brand images."""
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    for size in ICON_SIZES:
        icon = _draw_meter(size)
        name = "icon.png" if size == 256 else f"icon@{size // 256}x.png"
        icon.save(BRAND_DIR / name)
        print(f"wrote {BRAND_DIR / name}")

    logo = _draw_logo(LOGO_SIZE)
    logo.save(BRAND_DIR / "logo.png")
    print(f"wrote {BRAND_DIR / 'logo.png'}")


if __name__ == "__main__":
    main()
