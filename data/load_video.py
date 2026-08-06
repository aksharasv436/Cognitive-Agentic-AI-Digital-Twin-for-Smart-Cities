"""
load_video.py
==============
Loads the CCTV/video modality used by the Detection Agent (Stage A "3D-CNN
/ ViT-B encoder" block in Figure 2 of the DA1 report).

Datasets: UCF-Crime, ShanghaiTech Campus.

Why this script does NOT auto-download the raw video
------------------------------------------------------
Both datasets are large (UCF-Crime ~130 GB, ShanghaiTech ~40 GB) and are
distributed by their authors via Dropbox/OneDrive links that require manual,
click-through acceptance of a usage agreement — there is no stable
programmatic endpoint, and auto-downloading would silently break whenever
the maintainers rotate the link. Instead this script:

1. Prints the current official links + expected folder layout.
2. Once you've placed (or symlinked) the dataset under `--root`, indexes it
   and returns a manifest DataFrame (clip path, label, split) that a
   PyTorch `Dataset` can wrap directly.
3. Includes `make_demo_clips()` to synthesize a handful of tiny fake video
   files locally, purely so the rest of the pipeline (frame decoding, 3D-CNN
   input shaping) can be exercised end-to-end without the real dataset.

Usage
-----
    python data/load_video.py --root ./raw/UCF_Crime            # index real data
    python data/load_video.py --demo                            # synthetic smoke test

Official sources (as of the DA1 report date; verify before download)
----------------------------------------------------------------------
- UCF-Crime:      https://www.crcv.ucf.edu/projects/real-world/
- ShanghaiTech:   https://svip-lab.github.io/dataset/campus_dataset.html
"""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd

OFFICIAL_SOURCES = {
    "ucf-crime": "https://www.crcv.ucf.edu/projects/real-world/",
    "shanghaitech": "https://svip-lab.github.io/dataset/campus_dataset.html",
}


def index_local_dataset(root: str, extensions=(".mp4", ".avi", ".mkv")) -> pd.DataFrame:
    """
    Walk `root` and build a manifest. Expects a layout of
    `root/<label>/<clip files>` (standard for both UCF-Crime and
    ShanghaiTech after extraction) — adjust `infer_label` below if your
    local copy uses a different layout.
    """
    root_path = Path(root)
    if not root_path.exists():
        print(f"[load_video] '{root}' does not exist yet.\n"
              f"  Download the dataset manually from one of:\n"
              + "\n".join(f"    - {k}: {v}" for k, v in OFFICIAL_SOURCES.items())
              + f"\n  then extract it under '{root}' and re-run this script.",
              file=sys.stderr)
        sys.exit(1)

    rows = []
    for path in root_path.rglob("*"):
        if path.suffix.lower() in extensions:
            label = path.parent.name  # folder name = class label, e.g. "Robbery", "Normal"
            rows.append({"path": str(path), "label": label})

    if not rows:
        print(f"[load_video] No video files found under '{root}'. "
              f"Check the folder layout matches <root>/<label>/<clip>.{{mp4,avi,mkv}}",
              file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(rows)
    return df


def make_demo_clips(out_dir: str = "./cache/video_demo", n_clips: int = 4, seed: int = 0):
    """
    Generates tiny synthetic .mp4 clips (solid-color frames with random
    noise) purely to smoke-test the downstream loading/encoding pipeline
    without needing the real, license-gated dataset.
    Requires opencv-python.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("[load_video] Missing dependency 'opencv-python'. Install with: pip install opencv-python",
              file=sys.stderr)
        sys.exit(1)

    rng = np.random.default_rng(seed)
    os.makedirs(out_dir, exist_ok=True)
    labels = ["Normal", "Anomaly"]
    rows = []
    for i in range(n_clips):
        label = labels[i % 2]
        label_dir = Path(out_dir) / label
        label_dir.mkdir(parents=True, exist_ok=True)
        clip_path = label_dir / f"demo_{i:03d}.mp4"

        h, w, fps, n_frames = 224, 224, 10, 30
        writer = cv2.VideoWriter(str(clip_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        for _ in range(n_frames):
            frame = rng.integers(0, 255, (h, w, 3), dtype="uint8")
            writer.write(frame)
        writer.release()
        rows.append({"path": str(clip_path), "label": label})

    df = pd.DataFrame(rows)
    print(f"[load_video] Wrote {n_clips} synthetic demo clips to {out_dir}")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="local path to an extracted dataset")
    ap.add_argument("--demo", action="store_true", help="generate + index tiny synthetic clips instead")
    args = ap.parse_args()

    if args.demo:
        manifest = make_demo_clips()
    elif args.root:
        manifest = index_local_dataset(args.root)
    else:
        print("[load_video] Specify --root <path> for a real dataset, or --demo for a synthetic smoke test.\n"
              "Official sources:")
        for k, v in OFFICIAL_SOURCES.items():
            print(f"  - {k}: {v}")
        sys.exit(0)

    print(manifest.head())
    print(f"[load_video] Manifest size: {len(manifest)} clips, "
          f"labels: {sorted(manifest['label'].unique())}")
    print("[load_video] OK.")
