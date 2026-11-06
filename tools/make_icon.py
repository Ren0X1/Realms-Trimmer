"""Generates assets/icon.png and assets/icon.ico (needs Pillow; dev-only).

A pixel-art grass block with its lower-right corner trimmed away along a
dashed cut line, and a pair of scissors on the cut.
"""
import os
import random

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'assets')
S = 512  # master size

random.seed(7)
GRASS = [(106, 170, 60), (94, 156, 52), (122, 186, 72), (84, 140, 46)]
DIRT = [(134, 96, 67), (121, 85, 58), (150, 108, 76), (108, 76, 52)]


def master():
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded dark tile background
    d.rounded_rectangle((8, 8, S - 8, S - 8), radius=96, fill=(24, 28, 38, 255))

    # 12x12 pixel grass block
    n, x0, y0, px = 12, 64, 64, 32
    for gy in range(n):
        for gx in range(n):
            # Trimmed corner: cells below the anti-diagonal cut are removed
            if gx + gy >= 15:
                continue
            if gy < 3 or (gy == 3 and random.random() < 0.5):
                c = random.choice(GRASS)
            else:
                c = random.choice(DIRT)
            x, y = x0 + gx * px, y0 + gy * px
            d.rectangle((x, y, x + px - 1, y + px - 1), fill=c)

    # Dashed cut line along the trim
    a, b = (x0 + 15 * px - 12 * px + 8, y0 + 12 * px), (x0 + 12 * px, y0 + 15 * px - 12 * px + 8)
    steps = 9
    for i in range(steps):
        if i % 2:
            continue
        t0, t1 = i / steps, (i + 1) / steps
        p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
        p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
        d.line((p0, p1), fill=(255, 255, 255, 235), width=12)

    # Scissors (white blades, orange handles) on the cut
    cx, cy = 372, 372
    blade = (240, 244, 248, 255)
    handle = (245, 166, 35, 255)
    d.line(((cx - 96, cy - 30), (cx + 40, cy + 6)), fill=blade, width=22)
    d.line(((cx - 30, cy - 96), (cx + 6, cy + 40)), fill=blade, width=22)
    for hx, hy in ((cx + 62, cy + 26), (cx + 26, cy + 62)):
        d.ellipse((hx - 36, hy - 36, hx + 36, hy + 36), outline=handle, width=16)
    d.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill=(24, 28, 38, 255))
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    img = master()
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, 'icon.png'))
    img.save(os.path.join(OUT, 'icon.ico'),
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print('written to', os.path.abspath(OUT))


if __name__ == '__main__':
    main()
