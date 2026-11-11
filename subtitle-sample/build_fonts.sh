#!/usr/bin/env bash
# 准备样例所需的两款字体并安装到 ~/.fonts：
#   思源黑体 Medium       ← adobe-fonts/source-han-sans（release 分支）官方 OTF
#   Dream Han Sans J W16  ← 按 Pal3love/dream-han-cjk 的构建流程，从 SourceHanSans-VF 实例化
#                           （去掉 avar → wght=587.15 → 改名为 Dream Han Sans J W16）
# 依赖：git、python3、fonttools、skia-pathops（pip install fonttools skia-pathops）
set -euo pipefail

WORK="${WORK:-$(mktemp -d)}"
FONT_DIR="${FONT_DIR:-$HOME/.fonts}"
mkdir -p "$WORK" "$FONT_DIR"
cd "$WORK"

# 1) 思源黑体 SC Medium（官方静态字体，中文名 “思源黑体 Medium”）
if [ ! -f shs/OTF/SimplifiedChinese/SourceHanSansSC-Medium.otf ]; then
  git clone --depth 1 --filter=blob:none --no-checkout --branch release \
    https://github.com/adobe-fonts/source-han-sans shs
  git -C shs checkout HEAD -- OTF/SimplifiedChinese/SourceHanSansSC-Medium.otf
fi
cp shs/OTF/SimplifiedChinese/SourceHanSansSC-Medium.otf "$FONT_DIR/"

# 2) Dream Han Sans J W16
if [ ! -f dream/source/source-han-sans/SourceHanSans-VF.ttf ]; then
  git clone --depth 1 --filter=blob:none --no-checkout \
    https://github.com/Pal3love/dream-han-cjk dream
  git -C dream checkout HEAD -- source/source-han-sans/SourceHanSans-VF.ttf
fi
cp dream/source/source-han-sans/SourceHanSans-VF.ttf vf.ttf

python3 - <<'EOF'
from fontTools.ttLib import TTFont
f = TTFont("vf.ttf")
if "avar" in f:          # 与 dream-han-cjk/script/drop_avar_table.py 相同
    del f["avar"]
f.save("vf.ttf")
EOF

# W16 = 梦源黑体二次插值表第 16 档（build_fonts.sh: font_interpolations_quadratic）
fonttools varLib.instancer -q -o w16.ttf --remove-overlaps vf.ttf wght=587.15

python3 - <<'EOF'
from fontTools.ttLib import TTFont
f = TTFont("w16.ttf")
name = f["name"]
name.names = [r for r in name.names if r.nameID not in (1, 2, 3, 4, 6, 16, 17, 21, 22)]
en = {1: "Dream Han Sans J W16", 2: "Regular", 3: "P3LV;DreamHanSansJ-W16",
      4: "Dream Han Sans J W16", 6: "DreamHanSansJ-W16",
      16: "Dream Han Sans J", 17: "W16"}
ja = {1: "夢ノ角ゴ J W16", 2: "Regular", 4: "夢ノ角ゴ J W16",
      16: "夢ノ角ゴ J", 17: "W16"}
for nid, s in en.items():
    name.setName(s, nid, 3, 1, 0x409)
for nid, s in ja.items():
    name.setName(s, nid, 3, 1, 0x411)
name.setName("Version 3.03; Sans 2.005; Serif 2.003", 5, 3, 1, 0x409)
if "STAT" in f:          # 与 drop_STAT_table.py 相同
    del f["STAT"]
f["head"].yMax = f["hhea"].ascender   # 与 trim_head_ymax_ymin.py 相同
f["head"].yMin = f["hhea"].descender
f.save("DreamHanSansJ-W16.ttf")
EOF
cp DreamHanSansJ-W16.ttf "$FONT_DIR/"
rm -f vf.ttf w16.ttf

fc-cache -f "$FONT_DIR"
fc-list | grep -E "思源黑体 Medium|Dream Han Sans J W16"
