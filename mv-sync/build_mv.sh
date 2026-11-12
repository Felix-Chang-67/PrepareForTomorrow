#!/usr/bin/env bash
# 合成最终 MV：原视频 + 字幕 + Hi-Res 音轨
#
# 用法：./build_mv.sh <MV 视频> <字幕.ass> <音轨.flac|-> <输出文件> [soft|hard]
#   音轨写 "-" 表示保留 MV 原音轨（不移植）
#   soft（默认）：MKV，视频流原样拷贝（画质零损失），ASS 字幕轨 + 附带字体，需播放器支持 ASS（mpv / MPC / PotPlayer 等）
#   hard        ：字幕烧录进画面，视频重新编码（H.264 CRF 16，保留原分辨率/帧率/色彩参数/位深）
#                 输出 .mkv 时音轨为 24-bit FLAC；输出 .mp4 时为 24-bit ALAC（Apple 设备友好）
set -euo pipefail

MV="$1"; ASS="$2"; AUDIO="$3"; OUT="$4"; MODE="${5:-soft}"
FONT_DIR="${FONT_DIR:-$HOME/.fonts}"
FONTS=("$FONT_DIR/SourceHanSansSC-Medium.otf" "$FONT_DIR/DreamHanSansJ-W16.ttf")

if [ "$AUDIO" = "-" ]; then
  AIN=(); AMAP=(-map 0:a:0); ACODEC=(-c:a copy)
else
  AIN=(-i "$AUDIO"); AMAP=(-map 1:a:0)
  case "$OUT" in
    *.mp4|*.m4v|*.mov) ACODEC=(-c:a alac -sample_fmt s32p) ;;
    *)                 ACODEC=(-c:a copy) ;;
  esac
fi

if [ "$MODE" = "soft" ]; then
  case "$OUT" in *.mkv) ;; *) echo "soft 模式请输出 .mkv" >&2; exit 1 ;; esac
  ATTACH=()
  for f in "${FONTS[@]}"; do
    case "$f" in *.otf) mt=font/otf ;; *) mt=font/ttf ;; esac
    ATTACH+=(-attach "$f" "-metadata:s:t:$(( ${#ATTACH[@]} / 4 ))" "mimetype=$mt")
  done
  ffmpeg -hide_banner -y -i "$MV" "${AIN[@]}" -i "$ASS" \
    -map 0:v:0 "${AMAP[@]}" -map "$([ "$AUDIO" = "-" ] && echo 1 || echo 2):s" \
    -c:v copy "${ACODEC[@]}" -c:s ass \
    -metadata:s:s:0 language=chi -metadata:s:s:0 title="中日双语" -disposition:s:0 default \
    "${ATTACH[@]}" "$OUT"
else
  read -r PIXFMT CSPACE CPRIM CTRC CRANGE < <(ffprobe -v error -select_streams v:0 \
    -show_entries stream=pix_fmt,color_space,color_primaries,color_transfer,color_range \
    -of csv=p=0 "$MV" | tr ',' ' ')
  COLOR=()
  [ -n "${CSPACE:-}" ] && [ "$CSPACE" != "unknown" ] && COLOR+=(-colorspace "$CSPACE")
  [ -n "${CPRIM:-}" ] && [ "$CPRIM" != "unknown" ] && COLOR+=(-color_primaries "$CPRIM")
  [ -n "${CTRC:-}" ] && [ "$CTRC" != "unknown" ] && COLOR+=(-color_trc "$CTRC")
  [ -n "${CRANGE:-}" ] && [ "$CRANGE" != "unknown" ] && COLOR+=(-color_range "$CRANGE")
  ffmpeg -hide_banner -y -i "$MV" "${AIN[@]}" \
    -filter_complex "[0:v]ass='${ASS//\'/\\\'}'[v]" -map "[v]" "${AMAP[@]}" \
    -c:v libx264 -preset slow -crf 16 -pix_fmt "$PIXFMT" "${COLOR[@]}" \
    "${ACODEC[@]}" $(case "$OUT" in *.mp4|*.m4v|*.mov) echo -movflags +faststart ;; esac) "$OUT"
fi

ffprobe -v error -show_entries stream=index,codec_type,codec_name,width,height,sample_rate,bits_per_raw_sample \
  -of compact=p=0 "$OUT"
