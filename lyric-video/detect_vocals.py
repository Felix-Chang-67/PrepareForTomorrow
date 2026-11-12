#!/usr/bin/env python3
"""用 Demucs（htdemucs_ft 的 vocals 子模型）分离人声，输出人声能量包络，供 lrc2ass.py 判断每句唱完的时间。

  python3 detect_vocals.py song.wav --model 04573f0d-f3cf25b2.th -o vocals_env.npz [--save-vocals vocals.wav]

模型文件来自 Demucs 官方 htdemucs_ft（文件名后 8 位是 SHA256 前缀，加载前会校验）。
输出 npz：hop（秒）、db（每帧人声 RMS，dBFS）。
"""
import argparse
import hashlib
import subprocess
import sys

import numpy as np
import torch

SR = 44100
HOP = 0.01  # 10 ms


def read_audio(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "2", "-ar", str(SR),
         "-f", "f32le", "-"], check=True, capture_output=True).stdout
    return torch.from_numpy(np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.copy())


def load_vocals_model(path):
    prefix = path.rsplit("-", 1)[-1].split(".")[0]
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if not digest.startswith(prefix):
        sys.exit(f"模型校验失败：sha256 {digest[:16]}… 与文件名前缀 {prefix} 不符")
    from demucs.states import load_model
    # Demucs 的 .th 是带类信息的 pickle（已校验官方哈希），需 weights_only=False
    pkg = torch.load(path, map_location="cpu", weights_only=False)
    model = load_model(pkg)
    model.eval()
    return model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--model", required=True)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--save-vocals")
    args = ap.parse_args()

    from demucs.apply import apply_model

    model = load_vocals_model(args.model)
    mix = read_audio(args.audio)
    ref = mix.mean(0)
    mean, std = ref.mean(), ref.std()
    with torch.no_grad():
        out = apply_model(model, ((mix - mean) / std)[None], shifts=1, split=True,
                          overlap=0.25, progress=True, device="cpu")[0]
    vocals = out[model.sources.index("vocals")] * std + mean

    if args.save_vocals:
        pcm = vocals.T.contiguous().numpy().astype(np.float32).tobytes()
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2",
                        "-i", "-", args.save_vocals], input=pcm, check=True)

    mono = vocals.mean(0).numpy()
    hop = int(SR * HOP)
    n = len(mono) // hop
    frames = mono[: n * hop].reshape(n, hop)
    db = 10 * np.log10(np.maximum((frames ** 2).mean(1), 1e-12))
    np.savez(args.output, hop=HOP, db=db.astype(np.float32))
    print(f"{args.output}: {n} frames, peak {db.max():.1f} dBFS", file=sys.stderr)


if __name__ == "__main__":
    main()
