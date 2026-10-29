import os
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[2]
_candidates = [Path(os.environ["MODEL_DIR"]) if os.getenv("MODEL_DIR") else None,
               BASE / "models", BASE.parent / "backend" / "models", Path.cwd() / "backend" / "models"]
MODEL_DIR = next((c for c in _candidates if c and c.exists()), BASE / "models")
MODEL_PATHS = {"grid": MODEL_DIR / "grid_model.pkl", "traffic": MODEL_DIR / "traffic_model.pkl",
               "aqi": MODEL_DIR / "aqi_model.pkl"}

DOMAINS = ("grid", "traffic", "aqi")
FEATURES = {"grid": ["hour", "is_weekend", "temperature", "occupancy"],
            "traffic": ["hour", "is_weekend", "traffic_density"],
            "aqi": ["temperature", "traffic_density", "aqi"]}
ACTIONS = {"grid": ("Transformer Cooling & Load Shedding", "Grid Stable"),
           "traffic": ("Adaptive Signal Priority & EV Reroute", "Traffic Flow Normal"),
           "aqi": ("Municipal Air Scrubbers Activated", "Air Quality Acceptable")}

WARN, CRIT = 0.55, 0.78
HOPS = 2
DECAY = 0.60
AUTO_RESOLVE_AFTER = 5
SIM_TICK_SECONDS = float(os.getenv("SIM_TICK_SECONDS", "3"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]

SECTORS = ["Sector_A1", "Sector_A2", "Sector_B1", "Sector_B2", "Sector_C1", "Sector_C2"]
SECTOR_IDX = {s: i for i, s in enumerate(SECTORS)}

SECTOR_COORDS = {"Sector_A1": (34.0722, -118.2637), "Sector_A2": (34.0722, -118.2337),
                 "Sector_B1": (34.0722, -118.2037), "Sector_B2": (34.0322, -118.2637),
                 "Sector_C1": (34.0322, -118.2337), "Sector_C2": (34.0322, -118.2037)}


def build_coupling_matrix() -> np.ndarray:
    m = np.zeros((len(SECTORS), len(SECTORS)))
    for a in SECTORS:
        for b in SECTORS:
            if a == b:
                continue
            dy = round(abs(SECTOR_COORDS[a][0] - SECTOR_COORDS[b][0]) / 0.04)
            dx = round(abs(SECTOR_COORDS[a][1] - SECTOR_COORDS[b][1]) / 0.03)
            if dx + dy == 1:
                m[SECTOR_IDX[a], SECTOR_IDX[b]] = 0.4
            elif dx == 1 and dy == 1:
                m[SECTOR_IDX[a], SECTOR_IDX[b]] = 0.2
    return m


COUPLING_MATRIX = build_coupling_matrix()
HOPS, DECAY = 2, 0.8