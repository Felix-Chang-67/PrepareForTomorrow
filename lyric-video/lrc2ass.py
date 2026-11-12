#!/usr/bin/env python3
"""把“原文 + 中文翻译”双行 LRC 转成 ASS：中文在上（Default），原文在下（Default-L2）。

LRC 约定：
  * 同一时间戳出现两行时，第一行是原文，第二行是中文翻译；
  * 只有一行时视为没有翻译的原文（如英文句），翻译从 --extra-zh 表里查；
  * 空文本的时间戳表示上一句到此结束（间奏）。
每句的结束时间 = 下一个时间戳；最后一句结束于 --end（默认 +5 秒）。

给出 --vocal-env（detect_vocals.py 的输出）时，改为“唱完就消失”：
在 [本句开始, 下一时间戳) 内找最后一段持续 ≥ 0.15 秒、人声高于阈值的位置，
其结束点 + 尾音（默认 0.3 秒）就是本句结束；若离下一句不足 --min-gap 秒则直接接上，避免闪烁。
"""
import argparse
import re
import sys
from pathlib import Path

STYLES = """\
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,思源黑体 Medium,130,&H00FFFFFF,&H00FFFFFF,&H19533B3B,&H910E0807,0,0,0,0,100.0,100.0,0.0,0.0,1,5.0,1.2,2,135,135,100,1
Style: Default-L2,Dream Han Sans J W16,80,&H00FFFFFF,&H00FFFFFF,&H19000000,&H910E0807,0,0,0,0,100.0,100.0,0.0,0.0,1,3.0,0.0,2,135,135,35,1
"""

TAG_RE = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$")
META_RE = re.compile(r"^\[([a-z]+):(.*)\]$")


def parse_lrc(path):
    meta, entries = {}, []
    for raw in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        m = TAG_RE.match(line)
        if m:
            t = int(m.group(1)) * 60 + float(m.group(2))
            entries.append((t, m.group(3).strip()))
            continue
        m = META_RE.match(line)
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta, entries


def group(entries):
    """按时间戳合并：返回 [(t, [text, ...]), ...]，保持原顺序。"""
    groups = []
    for t, text in entries:
        if groups and abs(groups[-1][0] - t) < 1e-6:
            groups[-1][1].append(text)
        else:
            groups.append((t, [text]))
    return groups


def load_extra(path):
    table = {}
    if path:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                src, zh = line.split("\t", 1)
                table[src.strip()] = zh.strip()
    return table


class VocalEnds:
    def __init__(self, path, threshold, tail, min_gap, min_dur, min_seg=0.15, smooth=5):
        import numpy as np
        self.np = np
        d = np.load(path)
        self.hop = float(d["hop"])
        self.db = np.convolve(d["db"], np.ones(smooth) / smooth, mode="same")
        self.threshold, self.tail, self.min_gap = threshold, tail, min_gap
        self.min_dur, self.min_seg = min_dur, min_seg

    def end(self, start, nxt):
        np = self.np
        a, b = int(start / self.hop), int(nxt / self.hop)
        active = (self.db[a:b] > self.threshold).astype(int)
        edges = np.flatnonzero(np.diff(np.r_[0, active, 0]))
        segs = [(edges[i], edges[i + 1]) for i in range(0, len(edges), 2)
                if (edges[i + 1] - edges[i]) * self.hop >= self.min_seg]
        if not segs:
            return nxt
        e = max(start + segs[-1][1] * self.hop + self.tail, start + self.min_dur)
        return nxt if nxt - e < self.min_gap else e


def ass_time(t):
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def esc(text):
    return text.replace("{", "｛").replace("}", "｝").replace("\\", "＼")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lrc")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--extra-zh", help="TSV：原文<TAB>中文，用于 LRC 里没有翻译的句子")
    ap.add_argument("--end", type=float, help="最后一句的结束时间（秒）")
    ap.add_argument("--fade", type=int, default=150, help="淡入淡出毫秒数，0 为关闭")
    ap.add_argument("--title", nargs=2, metavar=("TOP", "BOTTOM"),
                    help="开头标题卡：上行（Default）与下行（Default-L2）文字")
    ap.add_argument("--title-time", nargs=2, type=float, default=(0.5, 3.4), metavar=("START", "END"))
    ap.add_argument("--vocal-env", help="detect_vocals.py 输出的 npz；给出后每句在唱完时消失")
    ap.add_argument("--vocal-threshold", type=float, default=-35.0, help="人声活跃阈值（dBFS）")
    ap.add_argument("--tail", type=float, default=0.3, help="唱完后再保留的秒数（含淡出）")
    ap.add_argument("--min-gap", type=float, default=0.5, help="与下一句间隔小于此值时直接接上")
    ap.add_argument("--min-dur", type=float, default=1.0, help="每句最短显示时长")
    args = ap.parse_args()

    meta, entries = parse_lrc(args.lrc)
    groups = group(entries)
    extra = load_extra(args.extra_zh)
    vocal = (VocalEnds(args.vocal_env, args.vocal_threshold, args.tail, args.min_gap, args.min_dur)
             if args.vocal_env else None)
    fad = f"{{\\fad({args.fade},{args.fade})}}" if args.fade > 0 else ""

    events, missing = [], []
    if args.title:
        a, b = args.title_time
        events.append((0, a, b, "Default", args.title[0]))
        events.append((1, a, b, "Default-L2", args.title[1]))

    for i, (t, texts) in enumerate(groups):
        texts = [x for x in texts if x]
        if not texts:
            continue  # 间奏标记，只用作上一句的结束时间
        end = groups[i + 1][0] if i + 1 < len(groups) else (args.end or t + 5.0)
        if vocal:
            end = vocal.end(t, end)
        original = texts[0]
        if len(texts) >= 2:
            zh = texts[1]
        else:
            zh = extra.get(original)
            if zh is None:
                missing.append(original)
        if zh:
            events.append((0, t, end, "Default", zh))
        events.append((1, t, end, "Default-L2", original))

    if missing:
        print("以下句子没有中文翻译（只显示原文）：", *sorted(set(missing)), sep="\n  ", file=sys.stderr)

    title = " - ".join(x for x in (meta.get("ar"), meta.get("ti")) if x) or "Lyrics"
    out = [
        "[Script Info]",
        f"Title: {title}",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "PlayResX: 3840",
        "PlayResY: 2160",
        "",
        STYLES,
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        "; 中文 = Default（Layer 0，在上）；原文 = Default-L2（Layer 1，在下）。",
        "; 分层是为了避免 libass 碰撞检测把下行顶到上方（两样式行框重叠 23px）。",
    ]
    for layer, s, e, style, text in events:
        out.append(f"Dialogue: {layer},{ass_time(s)},{ass_time(e)},{style},,0,0,0,,{fad}{esc(text)}")
    Path(args.output).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{args.output}: {len(events)} events", file=sys.stderr)


if __name__ == "__main__":
    main()
