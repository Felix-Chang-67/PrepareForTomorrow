#!/usr/bin/env python3
"""把音频版的 Hi-Res 音轨按 align_audio.py 的结果移植到 MV 时间轴，输出 24-bit / 48 kHz。

  python3 transplant_audio.py mv.mp4 ref.wav align.json -o hires.wav [--keep-mv 0-12.5,200-210]

  输出扩展名 .wav → 24-bit PCM（pcm_s24le）；.flac → 24-bit FLAC（无损压缩，解码后与 PCM 完全相同）。

  * 歌曲部分直接逐采样拷贝参考音频（偏移取整到采样），不做任何增益或重采样处理；
  * MV 独有的部分（片头片尾、插入内容）保留 MV 原音轨，并按 align 的电平差调到与参考一致；
  * 换接处 20 ms 交叉淡化；MV 剪辑点处两段参考音频之间同样交叉淡化；
  * --keep-mv 指定 MV 时间范围（秒）强制保留 MV 原音，例如有音效/对白叠在音乐上的地方；
  * 最后报告：逐采样一致的比例，以及 MV 与参考差异较大的时间段（可能有音效/对白/不同混音/淡出）。
"""
import argparse
import json
import subprocess
import sys

import numpy as np

SR = 48000


def decode(path, channels=2):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-ac", str(channels), "-ar", str(SR),
         "-af", "aresample=resampler=soxr:precision=28", "-f", "f32le", "-"],
        check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, channels).copy()


def ramp(n):
    return (np.arange(n, dtype=np.float32) + 0.5) / n


def parse_ranges(text):
    out = []
    for part in filter(None, (text or "").split(",")):
        a, b = part.split("-")
        out.append((float(a), float(b)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mv")
    ap.add_argument("reference")
    ap.add_argument("align")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--xfade", type=float, default=0.02)
    ap.add_argument("--keep-mv", help="MV 时间范围（秒），逗号分隔，如 0-12.5,200-210")
    ap.add_argument("--no-gain-match", action="store_true", help="MV 独有部分不做电平匹配")
    args = ap.parse_args()

    al = json.load(open(args.align, encoding="utf-8"))
    segs = al["segments"]
    mv = decode(args.mv)
    ref = decode(args.reference)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                            "stream=sample_rate", "-of", "csv=p=0", args.reference],
                           capture_output=True, text=True).stdout.strip()
    if probe != str(SR):
        print(f"注意：参考音频采样率为 {probe} Hz，已重采样到 48 kHz，不再是逐采样拷贝", file=sys.stderr)

    n = len(mv)
    xf = max(1, int(args.xfade * SR))
    g = 1.0 if args.no_gain_match else 10 ** (-al["gain_db"] / 20)
    base = mv * g                                   # MV 原音，电平对齐到参考
    R = np.zeros_like(base)                         # 移植的参考音频
    cover = np.zeros(n, dtype=np.float32)           # 1 = 用参考音频

    for k, s in enumerate(segs):
        shift = int(round(s["offset"] * SR))
        # 首段从参考开头、末段到参考结尾（避免时长取整丢掉首尾几个采样）
        a = 0 if k == 0 else int(round(s["ref_start"] * SR))
        b = len(ref) if k == len(segs) - 1 else min(int(round(s["ref_end"] * SR)), len(ref))
        ta, tb = max(a + shift, 0), min(b + shift, n)
        if tb <= ta:
            continue
        R[ta:tb] = ref[ta - shift: tb - shift]
        cover[ta:tb] = 1.0
        s["_t"] = (ta, tb, shift)

    # 段与段直接相接（剪掉一段）的地方：两段参考音频交叉淡化
    for s1, s2 in zip(segs, segs[1:]):
        if "_t" not in s1 or "_t" not in s2 or s1["_t"][1] != s2["_t"][0]:
            continue
        c, sh1, sh2 = s1["_t"][1], s1["_t"][2], s2["_t"][2]
        lo, hi = max(c - xf // 2, 0), min(c + xf - xf // 2, n)
        if lo - sh1 < 0 or hi - sh2 > len(ref) or hi - sh1 > len(ref) or lo - sh2 < 0:
            continue
        r = ramp(hi - lo)[:, None]
        R[lo:hi] = ref[lo - sh1: hi - sh1] * (1 - r) + ref[lo - sh2: hi - sh2] * r

    for a, b in parse_ranges(args.keep_mv):
        cover[int(a * SR): int(b * SR)] = 0.0

    # 参考 ↔ MV 原音 的换接处做淡化（在参考一侧内部完成，保持时长不变）
    edges = np.flatnonzero(np.diff(np.r_[0.0, (cover > 0).astype(np.float32), 0.0]))
    m = cover.copy()
    for e in edges:
        if e < n and (e == 0 or cover[e - 1] == 0) and cover[e] > 0 and e > 0:     # 0 → 1
            m[e: e + xf] = np.minimum(m[e: e + xf], ramp(min(xf, n - e)))
        elif e > 0 and cover[e - 1] > 0 and (e == n or cover[e] == 0) and e < n:   # 1 → 0
            lo = max(0, e - xf)
            m[lo:e] = np.minimum(m[lo:e], ramp(e - lo)[::-1])
    out = m[:, None] * R + (1 - m[:, None]) * base

    peak = float(np.abs(out).max())
    if peak > 1.0:
        print(f"注意：MV 独有部分电平匹配后峰值 {20 * np.log10(peak):+.2f} dBFS，已硬限幅到 0 dBFS；"
              "可加 --no-gain-match 或用 --keep-mv 调整", file=sys.stderr)
        out = np.clip(out, -1.0, 1.0)

    if args.output.lower().endswith(".flac"):
        codec = ["-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24"]
    else:
        codec = ["-c:a", "pcm_s24le"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                    *codec, args.output],
                   input=out.astype(np.float32).tobytes(), check=True)

    # ---- 报告 ----
    exact = m == 1.0
    print(f"{args.output}: {n / SR:.2f}s，其中 {exact.sum() / SR:.2f}s 为参考音频逐采样拷贝"
          f"（{100 * exact.mean():.1f}%），MV 原音 {(m == 0).sum() / SR:.2f}s")
    hop = SR // 2
    diff = []
    for i in range(0, n - hop, hop):
        if cover[i: i + hop].min() < 1:
            continue
        x, y = R[i: i + hop].mean(1), base[i: i + hop].mean(1)
        ex = np.sqrt(np.mean(x ** 2)) + 1e-9
        res = np.sqrt(np.mean((y - x) ** 2)) + 1e-9
        diff.append((i / SR, 20 * np.log10(res / ex)))
    flagged = [t for t, d in diff if d > -12]
    if diff:
        print(f"MV 与参考的差异（残差/信号，中位数）：{np.median([d for _, d in diff]):.1f} dB")
    if flagged:
        runs, start, prev = [], flagged[0], flagged[0]
        for t in flagged[1:]:
            if t - prev > 0.51:
                runs.append((start, prev + 0.5))
                start = t
            prev = t
        runs.append((start, prev + 0.5))
        print("MV 与参考差异明显（> −12 dB）的 MV 时间段——可能有音效/对白/不同混音/淡出，请人工确认：")
        for a, b in runs:
            print(f"  {a:7.2f}–{b:7.2f}s")


if __name__ == "__main__":
    main()
