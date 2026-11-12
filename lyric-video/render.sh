#!/usr/bin/env bash
# 用法：./render.sh <歌词.lrc> <音频> <封面> [输出目录]
# 生成 lyrics.ass、background.png 和 lyric_video_2160p.mp4（3840×2160、23.976fps、H.264 + AAC 320k）。
# 字体需先用 ../subtitle-sample/build_fonts.sh 安装。
set -euo pipefail

LRC="$1"; AUDIO="$2"; COVER="$3"; OUT_DIR="${4:-output}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT_DIR"

DUR=$(ffprobe -v error -select_streams a:0 -show_entries format=duration -of csv=p=0 "$AUDIO")

python3 "$HERE/lrc2ass.py" "$LRC" -o "$OUT_DIR/lyrics.ass" \
  --extra-zh "$HERE/extra_zh.tsv" --end "$DUR" ${TITLE_TOP:+--title "$TITLE_TOP" "$TITLE_BOTTOM"}

python3 "$HERE/make_background.py" "$COVER" -o "$OUT_DIR/background.png"

# RGB → BT.709 limited range 再叠字幕，避免默认 BT.601 矩阵导致的偏色
VF="scale=out_color_matrix=bt709:out_range=tv:flags=lanczos,format=yuv420p"
VF+=",setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
VF+=",ass=$OUT_DIR/lyrics.ass"

ffmpeg -hide_banner -y \
  -loop 1 -framerate 24000/1001 -i "$OUT_DIR/background.png" \
  -i "$AUDIO" \
  -filter_complex "[0:v]${VF}[v]" -map "[v]" -map 1:a:0 -t "$DUR" \
  -c:v libx264 -preset medium -crf 18 -tune stillimage \
  -profile:v high -level:v 5.1 -pix_fmt yuv420p \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -c:a aac -b:a 320k -ar 48000 \
  -movflags +faststart \
  "$OUT_DIR/lyric_video_2160p.mp4"
