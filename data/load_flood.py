"""
load_flood.py
==============
Loads the rainfall/water-level modality used by the flood-forecasting head
described in DA1 report Sections 2 and 4 (Transformer-LSTM style model,
following the Zhengzhou/Shenzhen study designs cited as [5],[6]).

As noted in the DA1 feasibility note (Section 5), per-district waterlogging
depth data is NOT publicly available for our target city. This script
therefore supports two modes:

1. --source usgs   : pulls real public streamflow/gauge data from the USGS
                      NWIS web service (requires network; free, no API key).
2. --source synthetic : generates a physically-plausible synthetic
                      rainfall -> water-depth dataset (no network required),
                      used as the stand-in surrogate dataset referenced in
                      the feasibility note's fallback plan.

Usage
-----
    python data/load_flood.py --source usgs --site 01646500 --days 30
    python data/load_flood.py --source synthetic --n-points 20 --days 60

Returns
-------
`load(...)` returns a pandas DataFrame indexed by timestamp, with one
column per monitored point/sensor (matching "IoT sensor time series ...
sampled every 5 minutes across a road/drainage network" in the DA1 problem
statement).
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd


def load_usgs(site: str = "01646500", days: int = 30, param_cd: str = "00065"):
    """
    Pull real gauge-height / discharge data from USGS NWIS (public, no key).
    param_cd 00065 = gauge height (ft); 00060 = discharge (cubic ft/s).
    """
    try:
        import requests
    except ImportError:
        print("[load_flood] Missing dependency 'requests'. Install with: pip install requests",
              file=sys.stderr)
        sys.exit(1)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    url = (
        "https://waterservices.usgs.gov/nwis/iv/"
        f"?format=json&sites={site}&parameterCd={param_cd}"
        f"&startDT={start:%Y-%m-%d}&endDT={end:%Y-%m-%d}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    series = payload["value"]["timeSeries"]
    if not series:
        raise RuntimeError(f"No data returned for site {site}. Check the site ID at "
                            f"https://waterdata.usgs.gov/nwis")

    values = series[0]["values"][0]["value"]
    df = pd.DataFrame(values)
    df["dateTime"] = pd.to_datetime(df["dateTime"])
    df["value"] = pd.to_numeric(df["value"])
    df = df.set_index("dateTime")[["value"]].rename(columns={"value": site})
    return df


def load_synthetic(n_points: int = 15, days: int = 30, freq_minutes: int = 5, seed: int = 42):
    """
    Generate a synthetic rainfall -> water-depth dataset for `n_points`
    drainage/waterlogging locations, following the event structure used in
    [5] (Zhengzhou: 15 monitored points, storm-event driven response).

    Each point's water depth responds to a shared city-wide rainfall signal
    with point-specific lag and gain, plus noise — enough structure for a
    forecasting model to learn a non-trivial signal while being fully
    reproducible offline.
    """
    rng = np.random.default_rng(seed)
    n_steps = int(days * 24 * 60 / freq_minutes)
    timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=n_steps, freq=f"{freq_minutes}min")

    # City-wide rainfall: a handful of storm bursts over the window
    rainfall = np.zeros(n_steps)
    n_storms = max(1, days // 7)
    for _ in range(n_storms):
        center = rng.integers(0, n_steps)
        width = rng.integers(20, 120)  # storm duration in steps
        intensity = rng.uniform(5, 40)  # mm/hr peak
        idx = np.arange(max(0, center - width), min(n_steps, center + width))
        rainfall[idx] += intensity * np.exp(-0.5 * ((idx - center) / (width / 3)) ** 2)
    rainfall = np.clip(rainfall, 0, None)

    data = {}
    for p in range(n_points):
        lag = rng.integers(1, 6)  # steps of delay for runoff to reach this point
        gain = rng.uniform(0.005, 0.02)  # m of depth per mm of rain
        decay = rng.uniform(0.85, 0.97)  # drainage recession rate per step
        depth = np.zeros(n_steps)
        for t in range(1, n_steps):
            inflow = gain * rainfall[max(0, t - lag)]
            depth[t] = decay * depth[t - 1] + inflow
        noise = rng.normal(0, 0.003, n_steps)
        data[f"point_{p:02d}_depth_m"] = np.clip(depth + noise, 0, None)

    df = pd.DataFrame(data, index=timestamps)
    df.insert(0, "rainfall_mm_hr", rainfall)
    return df


def load(source: str = "synthetic", **kwargs):
    if source == "usgs":
        return load_usgs(**{k: v for k, v in kwargs.items() if k in ("site", "days", "param_cd")})
    elif source == "synthetic":
        return load_synthetic(**{k: v for k, v in kwargs.items()
                                   if k in ("n_points", "days", "freq_minutes", "seed")})
    else:
        raise ValueError(f"Unknown source '{source}'. Use 'usgs' or 'synthetic'.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["usgs", "synthetic"], default="synthetic")
    ap.add_argument("--site", default="01646500", help="USGS site ID (source=usgs)")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--n-points", type=int, default=15, help="drainage points (source=synthetic)")
    ap.add_argument("--out", default=None, help="optional path to save CSV")
    args = ap.parse_args()

    print(f"[load_flood] Loading via '{args.source}' ...")
    df = load(args.source, site=args.site, days=args.days, n_points=args.n_points)
    print(df.head())
    print(f"[load_flood] Shape: {df.shape}")
    if args.out:
        df.to_csv(args.out)
        print(f"[load_flood] Saved to {args.out}")
    print("[load_flood] OK.")
