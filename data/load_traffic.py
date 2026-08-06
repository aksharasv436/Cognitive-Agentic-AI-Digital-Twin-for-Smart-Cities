"""
load_traffic.py
================
Loads the IoT/traffic time-series modality used by the Forecasting Agent
(Stage A / "Temporal GNN" encoder in Figure 2 of the DA1 report).

Datasets
--------
- METR-LA  : 207 sensors, LA county highway network, 5-min readings.
- PeMS-Bay : 325 sensors, Bay Area highway network, 5-min readings.

Both are fetched via `torch_geometric_temporal`, which downloads the
pre-processed adjacency matrix + node-feature tensors on first call and
caches them locally under `--cache-dir` (default: ./cache/traffic).

Usage
-----
    python data/load_traffic.py --dataset metr-la
    python data/load_traffic.py --dataset pems-bay --cache-dir ./cache/traffic

Returns
-------
`load(...)` returns a torch_geometric_temporal `StaticGraphTemporalSignal`
object: iterate over it to get one `torch_geometric.data.Data` snapshot per
timestep, each with `.x` (B x N x C node features) and `.edge_index` /
`.edge_weight` (static road-network topology) — matching the "IoT time
series B x L x C(sensors)" input block in Figure 2.

Notes
-----
- Requires network access on first run only (subsequent runs use the cache).
- If `torch_geometric_temporal` is not installed, this script prints the
  exact pip command and exits cleanly rather than raising a traceback.
"""
import argparse
import os
import sys


def _require(pkg_name, pip_name=None):
    try:
        return __import__(pkg_name)
    except ImportError:
        pip_name = pip_name or pkg_name
        print(f"[load_traffic] Missing dependency '{pkg_name}'. Install it with:\n"
              f"    pip install {pip_name}", file=sys.stderr)
        sys.exit(1)


def load(dataset: str = "metr-la", cache_dir: str = "./cache/traffic", num_timesteps_in: int = 12,
          num_timesteps_out: int = 12):
    """
    Parameters
    ----------
    dataset : {"metr-la", "pems-bay"}
    cache_dir : str
        Where torch_geometric_temporal should cache the raw download.
    num_timesteps_in / num_timesteps_out : int
        Sliding-window sizes for building (input, target) snapshot pairs,
        matching the forecasting-agent horizon H in Figure 2 (H=12 by default).

    Returns
    -------
    dataset : torch_geometric_temporal StaticGraphTemporalSignal
    """
    os.makedirs(cache_dir, exist_ok=True)
    cwd = os.getcwd()
    os.chdir(cache_dir)
    try:
        tgt = _require("torch_geometric_temporal")
        from torch_geometric_temporal.dataset import METRLADatasetLoader, PemsBayDatasetLoader

        if dataset == "metr-la":
            loader = METRLADatasetLoader()
        elif dataset == "pems-bay":
            loader = PemsBayDatasetLoader()
        else:
            raise ValueError(f"Unknown dataset '{dataset}'. Use 'metr-la' or 'pems-bay'.")

        signal = loader.get_dataset(
            num_timesteps_in=num_timesteps_in, num_timesteps_out=num_timesteps_out
        )
        return signal
    finally:
        os.chdir(cwd)


def preview(signal, n=3):
    print(f"Number of temporal snapshots: {signal.snapshot_count}")
    it = iter(signal)
    for i in range(n):
        snap = next(it)
        print(f"  snapshot {i}: x={tuple(snap.x.shape)} "
              f"edge_index={tuple(snap.edge_index.shape)} y={tuple(snap.y.shape)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", choices=["metr-la", "pems-bay"], default="metr-la")
    ap.add_argument("--cache-dir", default="./cache/traffic")
    ap.add_argument("--horizon-in", type=int, default=12)
    ap.add_argument("--horizon-out", type=int, default=12)
    args = ap.parse_args()

    print(f"[load_traffic] Loading {args.dataset} (cache: {args.cache_dir}) ...")
    ds = load(args.dataset, args.cache_dir, args.horizon_in, args.horizon_out)
    preview(ds)
    print("[load_traffic] OK.")
