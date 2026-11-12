#!/usr/bin/env python3
"""求 MV 音轨相对于参考音频（音频版 WAV）的时间对应关系，并逐段检查中间是否有剪辑。

  python3 align_audio.py ref.wav mv.mp4 -o align.json

做法：
  1. 把两边都解码成 4 kHz 单声道，参考音频按 8 秒窗、4 秒步长切开，
     每个窗在整条 MV 音轨里做归一化互相关（NCC），找出它在 MV 里的位置；
  2. 置信度够的窗再在 48 kHz 下 ±10 ms 内精修（抛物线插值，亚采样精度）；
  3. 偏移一致（±3 ms）的相邻窗归为一段；段与段之间用 1 秒小窗逐步比对两种偏移，定出剪辑点；
  4. 估计整体电平差（MV 相对参考，dB）和速度漂移（ppm）。

输出 JSON：segments（ref_start/ref_end/offset，MV 时间 = 参考时间 + offset）、gain_db、drift_ppm、windows。
"""
import argparse
import json
import subprocess
import sys

import numpy as np

SR_COARSE = 4000
SR_FINE = 48000
WIN, HOP = 8.0, 4.0
MIN_NCC = 0.5      # 低于此值的窗视为“对不上”
SAME_OFFSET = 0.003


def decode(path, sr, channels=1):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-ac", str(channels), "-ar", str(sr),
         "-af", "aresample=resampler=soxr", "-f", "f32le", "-"],
        check=True, capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    return x if channels == 1 else x.reshape(-1, channels)


def next_pow2(n):
    return 1 << (int(n) - 1).bit_length()


def ncc_search(window, target, target_fft=None, nfft=None):
    """window 在 target 中所有位置的归一化互相关；返回 (最佳起点, 峰值)。"""
    w = window - window.mean()
    wn = np.linalg.norm(w)
    if wn == 0:
        return 0, 0.0
    nfft = nfft or next_pow2(len(target) + len(w))
    tf = target_fft if target_fft is not None else np.fft.rfft(target, nfft)
    corr = np.fft.irfft(tf * np.conj(np.fft.rfft(w, nfft)), nfft)[: len(target) - len(w) + 1]
    c2 = np.concatenate([[0.0], np.cumsum(target.astype(np.float64) ** 2)])
    c1 = np.concatenate([[0.0], np.cumsum(target.astype(np.float64))])
    n = len(w)
    seg_energy = (c2[n:] - c2[:-n]) - (c1[n:] - c1[:-n]) ** 2 / n
    ncc = corr / (wn * np.sqrt(np.maximum(seg_energy, 1e-12)))
    i = int(np.argmax(ncc))
    return i, float(ncc[i])


def refine(ref48, tgt48, ref_start, offset, length=4.0, search=0.010):
    """48 kHz 下在 offset±search 内精修，返回 (offset, ncc)。"""
    a = int(ref_start * SR_FINE)
    w = ref48[a: a + int(length * SR_FINE)]
    s = int(round((ref_start + offset - search) * SR_FINE))
    e = s + len(w) + int(2 * search * SR_FINE)
    if s < 0 or e > len(tgt48) or len(w) == 0:
        return offset, 0.0
    seg = tgt48[s:e]
    w = w - w.mean()
    corr = np.correlate(seg - seg.mean(), w, mode="valid")
    k = int(np.argmax(corr))
    frac = 0.0
    if 0 < k < len(corr) - 1:
        y0, y1, y2 = corr[k - 1], corr[k], corr[k + 1]
        d = y0 - 2 * y1 + y2
        frac = 0.5 * (y0 - y2) / d if d != 0 else 0.0
    best = seg[k: k + len(w)]
    ncc = float(np.dot(best - best.mean(), w) / (np.linalg.norm(best - best.mean()) * np.linalg.norm(w) + 1e-12))
    return (s + k + frac) / SR_FINE - ref_start, ncc


def local_score(ref, tgt, t, offset, sr, length=1.0, search=0.0):
    """参考 [t, t+length) 与 MV [t+offset, …) 的 NCC；search>0 时在 ±search 内取最大。"""
    a, n = int(round(t * sr)), int(round(length * sr))
    if a < 0 or a + n > len(ref):
        return -1.0
    x = ref[a: a + n] - ref[a: a + n].mean()
    xn = np.linalg.norm(x)
    best = -1.0
    k = int(round(search * sr))
    for d in range(-k, k + 1):
        b = int(round((t + offset) * sr)) + d
        if b < 0 or b + n > len(tgt):
            continue
        y = tgt[b: b + n] - tgt[b: b + n].mean()
        best = max(best, float(np.dot(x, y) / (xn * np.linalg.norm(y) + 1e-12)))
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reference")
    ap.add_argument("target")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()

    ref = decode(args.reference, SR_COARSE)
    tgt = decode(args.target, SR_COARSE)
    ref48 = decode(args.reference, SR_FINE)
    tgt48 = decode(args.target, SR_FINE)
    ref_dur, tgt_dur = len(ref48) / SR_FINE, len(tgt48) / SR_FINE

    nfft = next_pow2(len(tgt) + int(WIN * SR_COARSE))
    tgt_fft = np.fft.rfft(tgt, nfft)
    loud = np.sqrt(np.mean(ref ** 2))

    # 第一遍：每个窗在整条 MV 音轨里的最佳位置
    raw = []
    t = 0.0
    while t + WIN <= ref_dur + 1e-6:
        a = int(t * SR_COARSE)
        w = ref[a: a + int(WIN * SR_COARSE)]
        rms = float(np.sqrt(np.mean(w ** 2)))
        if rms < loud * 0.05:  # 太安静（淡出、空白）的窗不参与
            raw.append((t, None, 0.0))
        else:
            pos, ncc = ncc_search(w, tgt, tgt_fft, nfft)
            raw.append((t, pos / SR_COARSE - t, ncc))
        t += HOP
    good = [round(o, 2) for _, o, c in raw if o is not None and c >= MIN_NCC]
    if not good:
        sys.exit("没有任何片段能对上：MV 音轨可能是另一版混音/重新录音，无法自动对齐。")
    vals, counts = np.unique(good, return_counts=True)
    prior = float(vals[np.argmax(counts)])

    # 第二遍：副歌等重复段落可能在别处也有同样高的匹配，若沿用上一个偏移几乎一样好，就沿用
    windows = []
    for t, off, ncc in raw:
        if off is None:
            windows.append({"ref_start": t, "status": "quiet"})
            continue
        entry = {"ref_start": t, "best_offset": round(off, 4), "best_ncc": round(ncc, 3)}
        keep = local_score(ref, tgt, t, prior, SR_COARSE, WIN, search=0.03)
        if keep >= ncc - 0.03:
            off = prior
        elif ncc < MIN_NCC:
            entry["status"] = "no-match"
            windows.append(entry)
            continue
        off_f, ncc_f = refine(ref48, tgt48, t + 2.0, off)
        if ncc_f < MIN_NCC:
            entry["status"] = "no-match"
            windows.append(entry)
            continue
        prior = off_f
        b = int((t + off_f) * SR_FINE)
        seg_t = tgt48[max(b, 0): max(b, 0) + int(WIN * SR_FINE)]
        seg_r = ref48[int(t * SR_FINE): int((t + WIN) * SR_FINE)]
        gain = 20 * np.log10((np.sqrt(np.mean(seg_t ** 2)) + 1e-12) / (np.sqrt(np.mean(seg_r ** 2)) + 1e-12))
        entry.update(offset=round(off_f, 6), ncc=round(ncc_f, 4), gain_db=round(float(gain), 2), status="ok")
        windows.append(entry)

    ok = [w for w in windows if w["status"] == "ok"]
    if not ok:
        sys.exit("没有任何片段能对上：MV 音轨可能是另一版混音/重新录音，无法自动对齐。")

    # 偏移一致的相邻窗归为一段
    groups = [[ok[0]]]
    for w in ok[1:]:
        if abs(w["offset"] - np.median([x["offset"] for x in groups[-1]])) <= SAME_OFFSET:
            groups[-1].append(w)
        else:
            groups.append([w])
    # 去掉只有 1 个窗、夹在同偏移两段之间的离群点
    merged = []
    for g in groups:
        if merged and len(g) == 1 and g is not groups[-1]:
            continue
        if merged and abs(np.median([x["offset"] for x in merged[-1]]) - np.median([x["offset"] for x in g])) <= SAME_OFFSET:
            merged[-1].extend(g)
        else:
            merged.append(g)

    segments = []
    for i, g in enumerate(merged):
        off = float(np.median([x["offset"] for x in g]))
        segments.append({"ref_start": g[0]["ref_start"], "ref_end": g[-1]["ref_start"] + WIN,
                         "offset": round(off, 6), "windows": len(g),
                         "ncc": round(float(np.median([x["ncc"] for x in g])), 4)})

    # 精定段落边界：在 MV 时间轴上以 0.05 s 步进、0.5 s 小窗比较两段偏移
    #   A 段最后吻合处 = c1，B 段开始持续吻合处 = c2；c2-c1 很小即“剪掉一段”，否则中间是 MV 独有内容
    L, STEP, GOOD = 0.5, 0.05, 0.6
    for a, b in zip(segments, segments[1:]):
        lo = a["ref_end"] - WIN + a["offset"]
        hi = b["ref_start"] + WIN + b["offset"]
        taus = np.arange(lo, hi, STEP)
        sa = np.array([local_score(ref48, tgt48, tau - a["offset"], a["offset"], SR_FINE, L) for tau in taus])
        sb = np.array([local_score(ref48, tgt48, tau - b["offset"], b["offset"], SR_FINE, L) for tau in taus])
        a_ok = (sa > GOOD) & (sa >= sb)
        b_ok = (sb > GOOD) & (sb > sa)
        # B 的最后一段连续吻合的起点
        idx = np.flatnonzero(b_ok)
        j = idx[-1] if len(idx) else len(taus) - 1
        while j > 0 and b_ok[j - 1]:
            j -= 1
        c2 = taus[j]
        before = np.flatnonzero(a_ok & (taus < c2))
        c1 = taus[before[-1]] + L if len(before) else c2
        if c1 >= c2 - 0.3:          # 直接相接：剪掉了一段 → 用 50 ms 小窗、5 ms 步进细扫定到 ~5 ms
            c = (min(c1, c2) + max(c1, c2)) / 2
            fl, fs = 0.05, 0.005
            ft = np.arange(c - 0.6, c + 0.6, fs)
            fa = np.array([local_score(ref48, tgt48, x - a["offset"], a["offset"], SR_FINE, fl) for x in ft])
            fb = np.array([local_score(ref48, tgt48, x - b["offset"], b["offset"], SR_FINE, fl) for x in ft])
            a_win = np.flatnonzero((fa > GOOD) & (fa > fb + 0.05))
            b_win = np.flatnonzero((fb > GOOD) & (fb > fa + 0.05))
            if len(a_win) and len(b_win):
                last_a = ft[a_win[a_win < b_win[-1]][-1]] + fl if (a_win < b_win[-1]).any() else c
                first_b = ft[b_win[b_win > a_win[0]][0]] if (b_win > a_win[0]).any() else c
                c = (last_a + first_b) / 2 if abs(last_a - first_b) < 0.1 else c
            c1 = c2 = round(float(c), 4)
        a["ref_end"] = round(c1 - a["offset"], 3)
        b["ref_start"] = round(c2 - b["offset"], 3)
        a["mv_gap_after"] = round(float(c2 - c1), 3)
    segments[0]["ref_start"] = 0.0
    segments[-1]["ref_end"] = round(ref_dur, 6)

    # 漂移：段内 offset 随时间的斜率
    drift = 0.0
    if len(segments) == 1 and len(ok) >= 3:
        drift = float(np.polyfit([w["ref_start"] for w in ok], [w["offset"] for w in ok], 1)[0] * 1e6)

    result = {
        "reference": args.reference, "target": args.target,
        "reference_duration": round(ref_dur, 3), "target_duration": round(tgt_dur, 3),
        "segments": segments,
        "gain_db": round(float(np.median([w["gain_db"] for w in ok])), 2),
        "drift_ppm": round(drift, 2),
        "matched_windows": len(ok), "total_windows": len(windows),
        "windows": windows,
    }
    json.dump(result, open(args.output, "w"), ensure_ascii=False, indent=1, default=float)

    print(f"参考 {ref_dur:.2f}s，MV 音轨 {tgt_dur:.2f}s，可对上的窗 {len(ok)}/{len(windows)}")
    for s in segments:
        print(f"  参考 {s['ref_start']:7.2f}–{s['ref_end']:7.2f}s → MV {s['ref_start'] + s['offset']:7.2f}–"
              f"{s['ref_end'] + s['offset']:7.2f}s  偏移 {s['offset']:+.4f}s  NCC {s['ncc']}")
    print(f"  电平差（MV − 参考）{result['gain_db']:+.2f} dB，速度漂移 {result['drift_ppm']:+.1f} ppm")
    bad = [w for w in windows if w["status"] == "no-match"]
    if bad:
        print("  对不上的窗：", ", ".join(f"{w['ref_start']:.0f}s" for w in bad))


if __name__ == "__main__":
    main()
