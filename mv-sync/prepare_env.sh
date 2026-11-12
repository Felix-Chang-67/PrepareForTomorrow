#!/usr/bin/env bash
# 在新的云端环境里恢复制作所需的一切。
#
# 用法：./prepare_env.sh [Google Drive 公开文件夹 ID] [素材下载目录]
#   1. Python 依赖：numpy fonttools skia-pathops matplotlib、CPU 版 torch + demucs
#   2. 字体：思源黑体 Medium、Dream Han Sans J W16（../subtitle-sample/build_fonts.sh）
#   3. Demucs htdemucs_ft 的 vocals 子模型（校验 SHA256）
#   4. 若给出 Drive 文件夹 ID：列出并下载其中所有文件（文件夹需“知道链接的人可查看”）
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FOLDER_ID="${1:-}"
DL_DIR="${2:-$HERE/../lyric-video/output/src}"
MODEL_DIR="${MODEL_DIR:-$HOME/.cache/mv-sync}"
MODEL="$MODEL_DIR/04573f0d-f3cf25b2.th"

echo "== Python 依赖"
pip install -q numpy fonttools skia-pathops matplotlib 2>&1 | grep -v "WARNING: Running pip as" || true
python3 -c "import torch" 2>/dev/null || \
  pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu 2>&1 | grep -v "WARNING: Running pip as" || true
python3 -c "import demucs" 2>/dev/null || pip install -q demucs 2>&1 | grep -v "WARNING: Running pip as" || true

echo "== 字体"
if fc-list | grep -q "思源黑体 Medium" && fc-list | grep -q "Dream Han Sans J W16"; then
  echo "已安装"
else
  "$HERE/../subtitle-sample/build_fonts.sh"
fi

echo "== 人声分离模型"
mkdir -p "$MODEL_DIR"
if [ ! -f "$MODEL" ]; then
  curl -sSL -o "$MODEL" "https://huggingface.co/dokodesuka/htdemucs_ft/resolve/main/04573f0d-f3cf25b2.th"
fi
sha256sum "$MODEL" | grep -q "^f3cf25b2" || { echo "模型 SHA256 校验失败" >&2; rm -f "$MODEL"; exit 1; }
echo "$MODEL"

if [ -n "$FOLDER_ID" ]; then
  echo "== 下载 Drive 文件夹 $FOLDER_ID → $DL_DIR"
  mkdir -p "$DL_DIR"
  curl -sSL "https://drive.google.com/embeddedfolderview?id=$FOLDER_ID" -o "$DL_DIR/.folder.html"
  python3 -I - "$DL_DIR/.folder.html" <<'EOF' > "$DL_DIR/.files.tsv"
import re, sys
h = open(sys.argv[1], encoding="utf-8").read()
for m in re.finditer(r'id="entry-([A-Za-z0-9_-]+)".*?flip-entry-title">([^<]+)<', h, re.S):
    name = m.group(2).replace("/", "_")
    print(f"{m.group(1)}\t{name}")
EOF
  while IFS=$'\t' read -r id name; do
    [ -f "$DL_DIR/$name" ] && { echo "  已存在 $name"; continue; }
    curl -sSL -o "$DL_DIR/$name" "https://drive.usercontent.google.com/download?id=$id&export=download&confirm=t"
    echo "  $(du -h "$DL_DIR/$name" | cut -f1)  $name"
  done < "$DL_DIR/.files.tsv"
fi

echo "== 完成。VOCAL_MODEL=$MODEL"
