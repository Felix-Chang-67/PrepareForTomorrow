#!/usr/bin/env bash
# 把 sample.ass 烧录到 3840×2160 / 23.976fps 的动态渐变背景上，输出 H.264 MP4，并导出预览截图。
# 需先运行 build_fonts.sh 安装字体；ffmpeg 需带 libass。
set -euo pipefail
cd "$(dirname "$0")"

OUT="${OUT:-subtitle_sample_2160p.mp4}"
DUR=34

BG="gradients=s=3840x2160:r=24000/1001:d=${DUR}"
BG+=":c0=0x0b1026:c1=0x2b6cb0:c2=0xf6ad55:c3=0xf7fafc:c4=0x38a169:c5=0x1a202c"
BG+=":nb_colors=6:speed=0.006:seed=7,vignette=PI/5"

ffmpeg -hide_banner -y \
  -f lavfi -i "${BG},format=yuv420p,ass=sample.ass" \
  -c:v libx264 -preset slow -crf 16 -aq-mode 3 \
  -profile:v high -level:v 5.1 -pix_fmt yuv420p \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -movflags +faststart \
  "$OUT"

# 每条字幕中点各截一帧
mkdir -p preview
i=1
for t in 2.5 7 11.5 16.25 21 25.5 30.5; do
  ffmpeg -hide_banner -v error -y -ss "$t" -i "$OUT" -frames:v 1 \
    "preview/$(printf '%02d' "$i")_${t}s.png"
  i=$((i + 1))
done
