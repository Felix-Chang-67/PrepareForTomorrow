# 双语歌词视频（2160p）

把“原文 + 中文翻译”的双行 LRC、音频和封面做成 3840×2160 歌词视频，字幕格式与 `../subtitle-sample` 相同：

- **中文在上**：`Default`（思源黑体 Medium 130）
- **原文（日文 / 英文）在下**：`Default-L2`（Dream Han Sans J W16 80）
- 每句 150 ms 淡入淡出（`\fad(150,150)`）

## 用法

```bash
../subtitle-sample/build_fonts.sh          # 先装字体（只需一次）
TITLE_TOP=歌名 TITLE_BOTTOM=歌手 \
  ./render.sh 歌词.lrc 音频.wav 封面.jpg output
```

输出到 `output/`（已加入 `.gitignore`，不会提交）：

| 文件 | 内容 |
|---|---|
| `lyrics.ass` | 由 LRC 转出的字幕 |
| `background.png` | 模糊压暗的封面铺底 + 居中封面 1400×1400 |
| `lyric_video_2160p.mp4` | 3840×2160 · 23.976 fps · H.264 High · BT.709 · AAC 320k / 48 kHz |

`TITLE_TOP` / `TITLE_BOTTOM` 可省略。设置后会在开头 0.5–3.4 秒用同样的上下两行样式显示一张标题卡。

## LRC 规则（`lrc2ass.py`）

- 同一时间戳有两行时：第一行是原文 → `Default-L2`，第二行是中文 → `Default`。
- 只有一行（例如没翻译的英文句）：原文放在下行，中文从 `extra_zh.tsv` 查找，查不到就只显示原文，并在终端里提示。
- 空文本的时间戳当作间奏标记，只用来结束上一句。
- 每句的结束时间是下一个时间戳；最后一句结束于音频结尾。
- 中文放在 Layer 0，原文放在 Layer 1。两个样式的行框重叠 23 px，同一 Layer 时 libass 会把下行顶到上方，分层后就不会。

## 为什么不把成片放进仓库

这个仓库是公开的，而歌曲音频、歌词全文和带完整音轨的视频都属于版权素材，所以只提交生成脚本，成片和素材留在本地的 `output/`。
