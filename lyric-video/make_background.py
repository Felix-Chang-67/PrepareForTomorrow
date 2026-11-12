#!/usr/bin/env python3
"""用封面生成 3840×2160 静态背景：铺满画面的模糊暗化封面 + 居中清晰封面（带柔和投影）。

封面下缘留出约 300px 给底部两行字幕（Default 行框顶端在 y=1930）。
"""
import argparse

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

W, H = 3840, 2160


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cover")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--size", type=int, default=1400, help="前景封面边长")
    ap.add_argument("--top", type=int, default=230, help="前景封面上边距")
    ap.add_argument("--blur", type=float, default=48)
    ap.add_argument("--brightness", type=float, default=0.32)
    args = ap.parse_args()

    cover = Image.open(args.cover).convert("RGB")

    # 背景：放大到宽度铺满 → 居中裁成 16:9 → 高斯模糊 → 压暗
    bg = cover.resize((W, W * cover.height // cover.width), Image.LANCZOS)
    top = (bg.height - H) // 2
    bg = bg.crop((0, top, W, top + H))
    bg = bg.filter(ImageFilter.GaussianBlur(args.blur))
    bg = ImageEnhance.Brightness(bg).enhance(args.brightness)

    # 底部渐暗，让字幕区更干净
    grad = Image.new("L", (1, H))
    for y in range(H):
        k = max(0.0, (y - H * 0.70) / (H * 0.30))
        grad.putpixel((0, y), int(150 * k ** 1.5))
    shade = Image.new("RGB", (W, H), (0, 0, 0))
    bg = Image.composite(shade, bg, grad.resize((W, H)))

    # 投影
    s = args.size
    x0, y0 = (W - s) // 2, args.top
    shadow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow).rectangle((x0, y0 + 30, x0 + s, y0 + s + 30), fill=200)
    shadow = shadow.filter(ImageFilter.GaussianBlur(45))
    bg = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), bg, shadow)

    # 前景封面
    bg.paste(cover.resize((s, s), Image.LANCZOS), (x0, y0))
    bg.save(args.output)


if __name__ == "__main__":
    main()
