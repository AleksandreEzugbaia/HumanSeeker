"""
Generate the HumanSeeker app icon (.ico) with multiple sizes for Windows.
Shield silhouette with an eye/scope motif, in a security-blue palette.
"""

import os
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
ICO_PATH = os.path.join(OUT_DIR, "frontend", "static", "icon.ico")
PNG_PATH = os.path.join(OUT_DIR, "frontend", "static", "icon.png")

os.makedirs(os.path.join(OUT_DIR, "frontend", "static"), exist_ok=True)


def make_icon(size: int) -> Image.Image:
    """Render the icon at the given square size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Background circle (deep navy)
    pad = int(size * 0.04)
    d.ellipse((pad, pad, size - pad, size - pad), fill=(15, 30, 60, 255))

    # Shield outline (lighter blue accent)
    shield_w = int(size * 0.55)
    shield_h = int(size * 0.62)
    shield_x = (size - shield_w) // 2
    shield_y = int(size * 0.18)

    # Build shield shape with rounded top, pointed bottom
    top = shield_y
    bottom = shield_y + shield_h
    mid = (top + bottom) // 2
    left = shield_x
    right = shield_x + shield_w
    cx = (left + right) // 2

    shield_points = [
        (left, top + int(shield_h * 0.15)),
        (cx, top),
        (right, top + int(shield_h * 0.15)),
        (right, mid + int(shield_h * 0.05)),
        (cx, bottom),
        (left, mid + int(shield_h * 0.05)),
    ]
    d.polygon(shield_points, fill=(40, 110, 200, 255))

    # Inner ring (the "scope" / behavioral eye)
    ring_d = int(size * 0.30)
    ring_x = cx - ring_d // 2
    ring_y = mid - ring_d // 2 - int(size * 0.02)
    d.ellipse(
        (ring_x, ring_y, ring_x + ring_d, ring_y + ring_d),
        outline=(255, 255, 255, 255),
        width=max(2, size // 64),
    )

    # Center dot (the pupil / human detector)
    dot_d = int(size * 0.10)
    dot_x = cx - dot_d // 2
    dot_y = mid - dot_d // 2 - int(size * 0.02)
    d.ellipse(
        (dot_x, dot_y, dot_x + dot_d, dot_y + dot_d),
        fill=(255, 215, 80, 255),  # amber accent
    )

    # Small "H" mark at the bottom of the shield to brand it
    if size >= 64:
        try:
            font = ImageFont.truetype("arialbd.ttf", int(size * 0.13))
        except OSError:
            font = ImageFont.load_default()
        text = "H"
        try:
            bbox = d.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except Exception:
            text_w, text_h = font.getsize(text) if hasattr(font, "getsize") else (size // 6, size // 6)
        tx = cx - text_w // 2
        ty = bottom - text_h - int(size * 0.10)
        d.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)

    return img


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [make_icon(s) for s in sizes]

    # Save the largest as PNG for use in pywebview's icon param (Windows takes .ico)
    images[-1].save(PNG_PATH, format="PNG")

    # Save .ico with multiple embedded resolutions
    images[0].save(
        ICO_PATH,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )

    print(f"Wrote icon: {ICO_PATH}")
    print(f"Wrote PNG: {PNG_PATH}")


if __name__ == "__main__":
    main()
