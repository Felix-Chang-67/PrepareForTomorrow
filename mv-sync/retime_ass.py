#!/usr/bin/env python3
"""按 align_audio.py 的结果，把基于音频版时间轴的 ASS 平移到 MV 时间轴（支持分段偏移）。

  python3 retime_ass.py lyrics.ass align.json -o lyrics_mv.ass

规则：落在某段内的时间点 t → t + 该段 offset；
      MV 剪掉的内容里的字幕会被裁掉或删除，跨越剪辑点的字幕结束于剪辑点，均会打印提示；
      结果限制在 [0, MV 时长] 内。
"""
import argparse
import json
import re
import sys

TIME = re.compile(r"(\d+):(\d{2}):(\d{2})\.(\d{2})")


def parse(ts):
    h, m, s, cs = map(int, TIME.fullmatch(ts).groups())
    return h * 3600 + m * 60 + s + cs / 100


def fmt(t):
    cs = max(0, int(round(t * 100)))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ass")
    ap.add_argument("align")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--min-trimmed", type=float, default=0.5, help="被剪辑点裁过的字幕短于此值（秒）则删除")
    args = ap.parse_args()

    al = json.load(open(args.align, encoding="utf-8"))
    segs = al["segments"]
    mv_dur = al["target_duration"]

    def seg_of(t):
        for i, s in enumerate(segs):
            lo = s["ref_start"] if i else float("-inf")
            hi = s["ref_end"] if i < len(segs) - 1 else float("inf")
            if lo <= t < hi:
                return i
        return None

    out, kept, dropped, trimmed = [], 0, 0, 0
    for line in open(args.ass, encoding="utf-8-sig"):
        if not line.startswith("Dialogue:"):
            out.append(line)
            continue
        head, rest = line.split(":", 1)
        f = rest.split(",", 9)
        start, end = parse(f[1].strip()), parse(f[2].strip())
        text = f[9].strip()
        i, j = seg_of(start), seg_of(end - 0.001)
        was_trimmed = False
        if i is None and j is None:
            print(f"  删除（内容已被 MV 剪掉）{f[1]}–{f[2]} {text[:30]}", file=sys.stderr)
            dropped += 1
            continue
        if i is None:                       # 开头落在被剪掉的部分
            i = j
            start = segs[j]["ref_start"]
            trimmed += 1
            was_trimmed = True
            print(f"  起点裁到剪辑点 {f[1]} {text[:30]}", file=sys.stderr)
        if j is None or j != i:             # 结尾跨过剪辑点
            end = segs[i]["ref_end"]
            j = i
            trimmed += 1
            was_trimmed = True
            print(f"  终点裁到剪辑点 {f[2]} {text[:30]}", file=sys.stderr)
        s2 = start + segs[i]["offset"]
        e2 = end + segs[j]["offset"]
        s2, e2 = max(0.0, s2), min(mv_dur, e2)
        if e2 - s2 < (args.min_trimmed if was_trimmed else 0.1):
            dropped += 1
            trimmed -= was_trimmed
            why = "落在 MV 时长之外" if (s2 >= mv_dur or e2 <= 0) else f"裁剪后只剩 {e2 - s2:.2f} 秒"
            print(f"  删除（{why}）{f[1]}–{f[2]} {text[:30]}", file=sys.stderr)
            continue
        f[1], f[2] = fmt(s2), fmt(e2)
        out.append(head + ":" + ",".join(f))
        kept += 1

    open(args.output, "w", encoding="utf-8").writelines(out)
    print(f"{args.output}: 保留 {kept}，裁剪 {trimmed}，删除 {dropped}", file=sys.stderr)


if __name__ == "__main__":
    main()
