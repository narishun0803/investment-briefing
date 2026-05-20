#!/usr/bin/env python3
"""Generate icon.ico for the investment briefing app."""

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow が必要です: pip3 install Pillow")
    raise


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    s = size

    # Background circle — dark navy
    d.ellipse([0, 0, s - 1, s - 1], fill=(15, 17, 23, 255))

    pad = s * 0.14
    w, h = s - pad * 2, s - pad * 2

    # Candlestick bars (simplified)
    bars = [
        # (x_frac, open_frac, close_frac, up?)
        (0.12, 0.55, 0.35, True),
        (0.28, 0.65, 0.45, True),
        (0.44, 0.50, 0.70, False),
        (0.60, 0.40, 0.20, True),
        (0.76, 0.30, 0.10, True),
    ]

    bar_w = w * 0.10
    for (xf, of_, cf, up) in bars:
        x  = pad + xf * w
        y0 = pad + min(of_, cf) * h
        y1 = pad + max(of_, cf) * h
        color = (34, 197, 94, 255) if up else (239, 68, 68, 255)
        d.rectangle([x - bar_w / 2, y0, x + bar_w / 2, y1], fill=color)
        # Wick
        wick_len = h * 0.06
        d.rectangle([x - 1, y0 - wick_len, x + 1, y0], fill=color)
        d.rectangle([x - 1, y1, x + 1, y1 + wick_len], fill=color)

    # Trend line — accent indigo
    pts = [(pad + xf * w, pad + cf * h) for (xf, _, cf, _) in bars]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        lw = max(2, s // 32)
        d.line([x0, y0, x1, y1], fill=(99, 102, 241, 230), width=lw)

    return img


def main():
    sizes = [16, 32, 48, 64, 128, 256]
    images = [make_icon(sz) for sz in sizes]

    out = Path(__file__).parent / "icon.ico"
    images[0].save(
        out,
        format="ICO",
        sizes=[(sz, sz) for sz in sizes],
        append_images=images[1:],
    )
    print(f"アイコン生成完了: {out}")

    # Also save PNG preview
    png_out = Path(__file__).parent / "icon_preview.png"
    make_icon(256).save(png_out)
    print(f"プレビュー: {png_out}")


if __name__ == "__main__":
    main()
