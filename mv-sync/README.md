# MV 字幕与 Hi-Res 音轨移植

把为音频版（Hi-Res WAV）做好的歌词字幕和音轨，对齐到 MV 的时间轴上。MV 的音乐起点可以和音频版不同，中间如果有剪辑或插入内容也能处理。

**成片音轨一律输出为 24-bit / 48 kHz PCM**：

- 能移植时，歌曲部分就是音频版 WAV 的原始采样，逐采样一致。
- 不能移植时（例如 MV 用了不同混音），把 MV 原音轨用 soxr 重采样到 48 kHz 后转成 24-bit PCM。这只统一了格式，有损压缩的音质不会因此变好。

MP4 不支持 PCM，所以成片容器用 MKV 或 MOV。

## 流程

```bash
# 0. 新环境先恢复依赖、字体、人声模型（Drive 文件夹 ID 作为参数传入，不写进仓库）
./prepare_env.sh <Drive 文件夹 ID> ../lyric-video/output/src

# 1. 音频版歌词字幕（中文在上 / 日文在下、唱完即消失）
VOCAL_MODEL=~/.cache/mv-sync/04573f0d-f3cf25b2.th \
  ../lyric-video/render.sh 歌词.lrc song.wav cover.jpg ../lyric-video/output   # 只要 lyrics.ass 时可中途停止

# 2. 对齐：MV 音轨 vs 音频版
python3 align_audio.py song.wav MV.mp4 -o align.json

# 3. 字幕平移到 MV 时间轴
python3 retime_ass.py ../lyric-video/output/lyrics.ass align.json -o lyrics_mv.ass

# 4. Hi-Res 音轨移植（24-bit / 48 kHz PCM WAV）
python3 transplant_audio.py MV.mp4 song.wav align.json -o hires_mv.wav [--keep-mv 起-止,…]

# 5. 合成
./build_mv.sh MV.mp4 lyrics_mv.ass hires_mv.wav MV_字幕.mkv soft   # 软字幕，视频零损失
./build_mv.sh MV.mp4 lyrics_mv.ass hires_mv.wav MV_字幕.mkv hard   # 硬字幕
./build_mv.sh MV.mp4 lyrics_mv.ass hires_mv.wav MV_字幕.mov hard   # 硬字幕，MOV 容器
./build_mv.sh MV.mp4 lyrics_mv.ass - MV_字幕.mkv soft               # 不移植：MV 原音转 24/48 PCM

# 去黑边后再烧字幕：先查黑边，再把字幕画布高度改成裁切后的高度（字号/边距保持原像素大小）
ffmpeg -i MV.mp4 -vf cropdetect=limit=24:round=2:reset=1 -f null - 2>&1 | grep -o "crop=[0-9:]*" | sort | uniq -c | sort -rn | head
sed -i 's/^PlayResY: 2160$/PlayResY: 1600/' lyrics_mv.ass
CROP=3840:1600:0:280 PRESET=medium CRF=18 ./build_mv.sh MV.mp4 lyrics_mv.ass hires_mv.wav MV_字幕.mov hard
```

## 各步骤说明

**`align_audio.py`**：参考音频按 8 秒窗切开，每个窗在整条 MV 音轨里做归一化互相关，再在 48 kHz 下精修到亚采样精度。

- 偏移一致的窗归为一段；段与段之间再细扫定出剪辑点，能区分“剪掉一段”（直接相接）和“插入了新内容”（中间有空档）。
- 副歌这类重复段落会优先沿用前一段的偏移，避免被匹配到另一次副歌、造成误判。
- 同时报告电平差（MV − 参考）和速度漂移；如果一个窗都对不上（MV 用的是不同混音或重新录音），会直接说明无法自动对齐。

**`retime_ass.py`**：按段平移字幕时间。

- 内容被 MV 剪掉的字幕直接删除。
- 跨越剪辑点的字幕裁到剪辑点为止；裁完不足 0.5 秒的也删除。
- 每一处改动都会打印出来。

**`transplant_audio.py`**：输出 24-bit / 48 kHz，扩展名为 `.wav` 时是 PCM，为 `.flac` 时是 FLAC。

- **歌曲部分**：参考音频逐采样原样拷贝，偏移取整到采样，不做增益、不重采样、不加抖动。
- **MV 独有部分**（片头片尾、插入段）：保留 MV 原音，并按电平差调到与 Hi-Res 一致。
- **换接处**：参考与 MV 原音之间、剪辑点两侧，都做 20 ms 交叉淡化。
- **差异报告**：列出 MV 与参考差异超过 −12 dB 的时间段。这些地方可能叠了音效或对白、用了不同混音，或者 MV 自己做了淡出。确认后可以用 `--keep-mv` 保留 MV 原音。

**`build_mv.sh`**

- **音轨**：一律输出 `pcm_s24le` 48 kHz。输入已经是 48 kHz 时不做任何处理，直接逐采样通过。
- **soft 模式**：MKV，视频流原样拷贝，ASS 字幕轨附带两款字体。需要支持 ASS 的播放器，例如 mpv、MPC-HC、PotPlayer、IINA。
- **hard 模式**：字幕烧录进画面，用 x264 重新编码（默认 slow / CRF 16，可用 `PRESET`、`CRF` 调整；固定开启 aq-mode 3，让暗部多分配码率、减少色带），保留原帧率、位深和色彩参数，可输出 MKV 或 MOV。设置 `CROP=w:h:x:y` 时，会先裁切再烧字幕。字幕是按 3840×2160 设计的（PlayRes 3840×2160），MV 是 1080p 等其他分辨率时，libass 会自动等比缩放。

## 测试

用音频版 WAV 模拟了三种 MV（转成 AAC 44.1 kHz、改变音量、带视频轨）：

| 模拟情况 | 对齐结果 | 字幕 | Hi-Res 移植 |
|---|---|---|---|
| A：加 6.4 s 片头、3 s 片尾，−2 dB，50–51 s 叠音效 | 偏移 +6.4000 s，−2.06 dB，漂移 −0.1 ppm | 80 句全部平移 | 167 s 逐采样一致；音效段被标记出来，用 `--keep-mv` 后保留了音效 |
| B：从 1.5 s 开始，剪掉间奏 61–68 s | 两段 −1.5 / −8.5 s，剪辑点误差 10 ms | 80 句全部平移 | 两段除 20 ms 淡化外逐采样一致 |
| C：剪掉人声段 20–25 s | 两段 0 / −5 s，剪辑点 20.00 / 25.00 s | 删除 2 句（整句被剪）+ 2 句（只剩 0.14 s），2 句从剪辑点开始 | 逐采样一致 |

合成到 MKV（软字幕）和 MOV（硬字幕）之后，测试 A 的歌曲部分（167 s）在成片 PCM 音轨里仍与原始 24-bit WAV 逐采样一致。
