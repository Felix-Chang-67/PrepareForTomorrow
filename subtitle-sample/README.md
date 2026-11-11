# 字幕样式样例视频（2160p）

`subtitle_sample_2160p.mp4`：3840×2160、23.976 fps、H.264，时长 34 秒，字幕已烧录。中文用 `Default`（在上），日文用 `Default-L2`（在下）。

| 样式 | 字体 | 字号 | 主色 | 边框色 | 阴影色 | 边框 / 阴影 | 对齐 | MarginL/R/V |
|---|---|---|---|---|---|---|---|---|
| Default | 思源黑体 Medium | 130 | 白 | `&H19533B3B`（#3B3B53，α=0x19） | `&H910E0807`（#07080E，α=0x91） | 5.0 / 1.2 | 2（底部居中） | 135 / 135 / 100 |
| Default-L2 | Dream Han Sans J W16 | 80 | 白 | `&H19000000`（黑，α=0x19） | `&H910E0807` | 3.0 / 0 | 2（底部居中） | 135 / 135 / 35 |

`PlayResX/PlayResY = 3840×2160`，所以样式里的数值就是 4K 画面上的像素。

## 内容

| 时间 | 测试项 |
|---|---|
| 0:00.5–0:09 | 普通对白（两句） |
| 0:09.5–0:13.5 | 「」引号、问号 |
| 0:14–0:18.5 | 超长中文句，超出左右边距后自动换行成两行（向上增长） |
| 0:19–0:23 | 中文 + 英文 + 数字混排，日文行带全套 Latin/数字 |
| 0:23.5–0:27.5 | 省略号、感叹号、波浪线 |
| 0:28–0:33 | 短句 |

画面左上、右上的小字是 `Info` / `InfoR` 角标，只用来标注参数和测试项，不属于被测样式。背景是缓慢流动的彩色渐变，会扫过亮、暗区域，用来检查描边的可读性。

## 注意：两条字幕的行框会互相碰撞

Default 行框为 y = 2160−100−130 … 2160−100 = **1930–2060**，
Default-L2 行框为 y = 2160−35−80 … 2160−35 = **2045–2125**，两者垂直重叠 15 px；
libass 的碰撞框还会把描边算进去（5 + 3），所以实际重叠 **23 px**。

如果两条事件在**同一个 Layer**，libass（mpv、Aegisub、ffmpeg 都用它）的碰撞检测会把后读到的那条往上推，结果日文跑到中文上方。
本样例把日文事件放在 `Layer 1`、中文放在 `Layer 0`，两者各自按 MarginV 定位，才是“中文在上、日文在下”的效果。
实际做字幕时，请用同样的分层；或者把 Default 的 MarginV 调到 **≥ 123**（用 libass 实测：122 仍会被顶上去，123 起日文留在下方），但这样中文会整体上移 23 px。

此外，按这组边距，中文行里拉丁字母的下伸部分（如 `p`、`g`）离日文行只有几个像素，见 `preview/05_21s.jpg`。

## 字体来源

- **思源黑体 Medium**：Adobe 官方 `SourceHanSansSC-Medium.otf`（中文 name 表里的家族名就是“思源黑体 Medium”）。
- **Dream Han Sans J W16**：GitHub release 下载不了，所以按 [dream-han-cjk](https://github.com/Pal3love/dream-han-cjk) 自己的构建流程，从仓库里的 `SourceHanSans-VF.ttf` 生成：去掉 `avar` → `wght=587.15`（W16 档）实例化并去除重叠 → 改名。
  它没有经过原项目用的 `otrebuild`（改 UPM 为 2048、去掉 hinting），所以字形相同，但文件和官方发布的版本并不逐字节一致。

## 重新生成

```bash
pip install fonttools skia-pathops
./build_fonts.sh     # 下载并生成两款字体，装到 ~/.fonts
./render.sh          # 输出 subtitle_sample_2160p.mp4 和 preview/*.jpg
```

`render.sh` 运行时，ffmpeg 日志里应能看到两行 `fontselect`，确认没有回退到其他字体：

```
fontselect: (思源黑体 Medium, 400, 0) -> .../SourceHanSansSC-Medium.otf
fontselect: (Dream Han Sans J W16, 400, 0) -> .../DreamHanSansJ-W16.ttf
```
