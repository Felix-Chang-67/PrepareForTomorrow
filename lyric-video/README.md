# 双语歌词视频（2160p）

把“原文 + 中文翻译”的双行 LRC、音频和封面做成 3840×2160 歌词视频，字幕格式与 `../subtitle-sample` 相同：

- **中文在上**：`Default`（思源黑体 Medium 130）
- **原文（日文 / 英文）在下**：`Default-L2`（Dream Han Sans J W16 80）
- 每句 150 ms 淡入淡出（`\fad(150,150)`）

## 用法

```bash
../subtitle-sample/build_fonts.sh          # 先装字体（只需一次）
pip install fonttools skia-pathops numpy
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu && pip install demucs

# 人声分离模型：Demucs 官方 htdemucs_ft 的 vocals 子模型
curl -L -o 04573f0d-f3cf25b2.th \
  https://huggingface.co/dokodesuka/htdemucs_ft/resolve/main/04573f0d-f3cf25b2.th

VOCAL_MODEL=04573f0d-f3cf25b2.th ./render.sh 歌词.lrc 音频.wav 封面.jpg output
```

不设 `VOCAL_MODEL` 时不做人声检测，每句一直显示到下一句开始。

输出到 `output/`（已加入 `.gitignore`，不会提交）：

| 文件 | 内容 |
|---|---|
| `vocals_env.npz` | 人声能量包络（10 ms 一帧），存在时直接复用，不再重新分离 |
| `lyrics.ass` | 由 LRC 转出的字幕 |
| `background.png` | 模糊压暗的封面铺底 + 居中封面 1400×1400 |
| `lyric_video_2160p.mp4` | 3840×2160 · 23.976 fps · H.264 High · BT.709 · AAC 320k / 48 kHz |

画面里只有歌词。如果需要在开头加标题卡，可以设置 `TITLE_TOP=歌名 TITLE_BOTTOM=歌手`。

## 唱完即消失（`detect_vocals.py` + `--vocal-env`）

LRC 只有每句的开始时间，所以要用 Demucs 把人声从伴奏里分离出来，再按 10 ms 一帧计算人声音量：

1. 在“本句开始 → 下一个时间戳”之间，找最后一段持续 ≥ 0.15 秒、人声高于 −35 dBFS 的片段；
2. 这段的结束点加 0.3 秒尾音（150 ms 淡出就在其中完成），就是本句的结束时间，并且每句至少显示 1 秒；
3. 如果离下一句不到 0.5 秒，就直接接上下一句，避免字幕闪一下又出现。

模型加载前会校验 SHA256 与文件名里的官方前缀（`f3cf25b2`）一致。阈值可以用 `--vocal-threshold`、`--tail`、`--min-gap`、`--min-dur` 调整。

## LRC 规则（`lrc2ass.py`）

- 同一时间戳有两行时：第一行是原文 → `Default-L2`，第二行是中文 → `Default`。
- 只有一行（例如没翻译的英文句）：原文放在下行，中文从 `extra_zh.tsv` 查找，查不到就只显示原文，并在终端里提示。
- 空文本的时间戳当作间奏标记，只用来结束上一句。
- 不做人声检测时，每句的结束时间是下一个时间戳，最后一句结束于音频结尾；做人声检测时见上一节。
- 中文放在 Layer 0，原文放在 Layer 1。两个样式的行框重叠 23 px，同一 Layer 时 libass 会把下行顶到上方，分层后就不会。

## 为什么不把成片放进仓库

这个仓库是公开的，而歌曲音频、歌词全文和带完整音轨的视频都属于版权素材，所以只提交生成脚本，成片和素材留在本地的 `output/`。
