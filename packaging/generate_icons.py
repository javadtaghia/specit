"""Generate SPECiT ('Si') Toyota-Red app icons (.png, .ico, and macOS .icns)."""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path(__file__).resolve().parent / 'icons'


def _load_bold_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        # macOS
        '/System/Library/Fonts/SFNS.ttf',
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
        # Windows
        'C:/Windows/Fonts/segoeuib.ttf',
        'C:/Windows/Fonts/arialbd.ttf',
        # Linux
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_si_icon(size: int = 1024) -> Image.Image:
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = int(size * 0.06)
    radius = int(size * 0.22)

    # Toyota Red gradient-like rounded square (two-tone vertical blend)
    base = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(base)
    top_rgb = (235, 10, 30)     # #EB0A1E
    bot_rgb = (184, 7, 23)      # #B80717
    for y in range(pad, size - pad):
        t = (y - pad) / max(1, (size - 2 * pad))
        c = tuple(int(top_rgb[i] * (1 - t) + bot_rgb[i] * t) for i in range(3)) + (255,)
        bdraw.line([(pad, y), (size - pad, y)], fill=c)

    mask = Image.new('L', (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=radius, fill=255)
    img.paste(base, (0, 0), mask)

    # Subtle inner highlight border
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [pad + 4, pad + 4, size - pad - 4, size - pad - 4],
        radius=max(4, radius - 4),
        outline=(255, 255, 255, 45),
        width=max(2, size // 128),
    )

    # Crisp centered "Si" mark
    font = _load_bold_font(int(size * 0.54))
    text = 'Si'
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) / 2 - bbox[0]
    ty = (size - th) / 2 - bbox[1] - size * 0.02

    # Soft drop shadow
    draw.text((tx, ty + size * 0.015), text, font=font, fill=(90, 0, 10, 120))
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))
    return img


def build_icons() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    master = render_si_icon(1024)
    png_path = OUT_DIR / 'specit.png'
    ico_path = OUT_DIR / 'specit.ico'

    master.save(png_path, format='PNG')
    master.save(
        ico_path,
        format='ICO',
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f'Generated {png_path} and {ico_path}')

    if platform.system() == 'Darwin' and shutil.which('iconutil'):
        iconset = OUT_DIR / 'specit.iconset'
        if iconset.exists():
            shutil.rmtree(iconset)
        iconset.mkdir(parents=True, exist_ok=True)
        for sz in (16, 32, 128, 256, 512):
            master.resize((sz, sz), Image.LANCZOS).save(iconset / f'icon_{sz}x{sz}.png')
            master.resize((sz * 2, sz * 2), Image.LANCZOS).save(iconset / f'icon_{sz}x{sz}@2x.png')
        icns_path = OUT_DIR / 'specit.icns'
        subprocess.run(['iconutil', '-c', 'icns', str(iconset), '-o', str(icns_path)], check=True)
        shutil.rmtree(iconset, ignore_errors=True)
        print(f'Generated {icns_path}')


if __name__ == '__main__':
    build_icons()
