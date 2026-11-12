#!/usr/bin/env bash
# 合成最终 MV：原视频 + 字幕 + 24-bit / 48 kHz PCM 音轨
#
# 用法：./build_mv.sh <MV 视频> <字幕.ass> <音轨.wav|.flac|-> <输出文件.mkv|.mov> [soft|hard]
#   音轨写 "-" 表示不移植 Hi-Res，把 MV 原音轨重采样到 48 kHz（soxr）后转成 24-bit PCM
#   音轨统一输出为 PCM 24-bit / 48 kHz（MKV: A_PCM/INT/LIT，MOV: lpcm）；MP4 不支持 PCM，故不提供
#   soft（默认）：MKV，视频流原样拷贝（画质零损失），ASS 字幕轨 + 附带字体，需播放器支持 ASS（mpv / MPC / PotPlayer 等）
#   hard        ：字幕烧录进画面，视频重新编码（H.264，保留原帧率/色彩参数/位深），输出 .mkv 或 .mov
#
# 环境变量（hard 模式）：
#   CROP=w:h:x:y   先裁切（例如去黑边 CROP=3840:1600:0:280），再烧字幕；字幕的 PlayRes 应设为裁切后尺寸
#   PRESET / CRF   x264 预设与质量，默认 slow / 16；另外固定开启 aq-mode 3（暗部多分配码率，减少色带）
set -euo pipefail

MV="$1"; ASS="$2"; AUDIO="$3"; OUT="$4"; MODE="${5:-soft}"
FONT_DIR="${FONT_DIR:-$HOME/.fonts}"
FONTS=("$FONT_DIR/SourceHanSansSC-Medium.otf" "$FONT_DIR/DreamHanSansJ-W16.ttf")

case "$OUT" in
  *.mkv|*.mov) ;;
  *) echo "输出请用 .mkv 或 .mov（MP4 不支持 PCM 音轨）" >&2; exit 1 ;;
esac

if [ "$AUDIO" = "-" ]; then
  AIN=(); AMAP=(-map 0:a:0)
else
  AIN=(-i "$AUDIO"); AMAP=(-map 1:a:0)
fi
# 已是 48 kHz 时 aresample 不做任何处理（逐采样直通）；44.1 kHz 等则用 soxr 高精度重采样
ACODEC=(-af "aresample=48000:resampler=soxr:precision=28" -c:a pcm_s24le -ar 48000)

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
  VF="ass='${ASS//\'/\\\'}'"
  [ -n "${CROP:-}" ] && VF="crop=${CROP},${VF}"
  ffmpeg -hide_banner -y -i "$MV" "${AIN[@]}" \
    -filter_complex "[0:v]${VF}[v]" -map "[v]" "${AMAP[@]}" \
    -c:v libx264 -preset "${PRESET:-slow}" -crf "${CRF:-16}" -aq-mode 3 -pix_fmt "$PIXFMT" "${COLOR[@]}" \
    "${ACODEC[@]}" $(case "$OUT" in *.mov) echo -movflags +faststart ;; esac) "$OUT"
fi

ffprobe -v error -show_entries stream=index,codec_type,codec_name,width,height,sample_rate,bits_per_raw_sample \
  -of compact=p=0 "$OUT"
