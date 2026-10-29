from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "backend" / "models"
RNG = np.random.default_rng(42)
SAMPLES = 12000

def clip01(values):
    return np.clip(values, 0.0, 1.0)

def make_clock(n):
    hour = RNG.integers(0, 24, size=n)
    is_weekend = (RNG.random(n) < (2 / 7)).astype(int)
    rush = (
        ((hour >= 7) & (hour <= 10)) |
        ((hour >= 16) & (hour <= 19))
    ).astype(float)
    return hour, is_weekend, rush

def make_traffic_data(n=SAMPLES):
    hour, is_weekend, rush = make_clock(n)
    traffic_density = np.clip(
        28 + 24 * rush - 8 * is_weekend + RNG.normal(0, 11, n),
        0, 100,
    )

    density_risk = clip01((traffic_density - 45) / 45)
    score = 0.70 * density_risk + 0.30 * rush
    labels = (score >= 0.50).astype(int)

    X = pd.DataFrame({
        "hour": hour,
        "is_weekend": is_weekend,
        "traffic_density": traffic_density,
    })
    return X, labels

def make_grid_data(n=SAMPLES):
    hour, is_weekend, _ = make_clock(n)

    temperature = np.clip(RNG.normal(27, 3.2, n), 18, 40)
    occupancy = np.clip(RNG.normal(320, 140, n), 40, 800)

    heat_stress = clip01((temperature - 30) / 8)
    load_stress = clip01((occupancy - 400) / 350)

    score = 0.55 * heat_stress + 0.45 * load_stress
    labels = (score >= 0.30).astype(int)

    X = pd.DataFrame({
        "hour": hour,
        "is_weekend": is_weekend,
        "temperature": temperature,
        "occupancy": occupancy,
    })

    return X, labels

def make_aqi_data(n=SAMPLES):
    hour, is_weekend, rush = make_clock(n)
    temperature = np.clip(RNG.normal(27, 5, n), 10, 43)

    traffic_density = np.clip(
        28 + 24 * rush - 8 * is_weekend + RNG.normal(0, 11, n),
        0, 100,
    )
    aqi = np.clip(
        RNG.normal(45, 18, n)
        + 0.45 * traffic_density
        + 1.8 * np.maximum(temperature - 30, 0),
        5, 300,
    )

    pollution_risk = clip01((aqi - 50) / 150)
    traffic_risk = clip01((traffic_density - 45) / 55)
    heat_risk = clip01((temperature - 30) / 10)
    score = (
        0.78 * pollution_risk
        + 0.14 * traffic_risk
        + 0.08 * heat_risk
    )
    labels = (score >= 0.45).astype(int)

    X = pd.DataFrame({
        "temperature": temperature,
        "traffic_density": traffic_density,
        "aqi": aqi,
    })
    return X, labels

def train_model(name, X, y):
    if len(np.unique(y)) < 2:
        raise RuntimeError(f"{name}: training data contains only one class")

    model = RandomForestClassifier(
        n_estimators=250,
        max_depth=10,
        min_samples_leaf=8,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X, y)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / f"{name}_model.pkl"
    joblib.dump(model, path)

    print(
        f"{name}: saved {path} | "
        f"hazard samples={np.mean(y):.1%} | "
        f"features={list(X.columns)}"
    )

def train_traffic_model():
    X, y = make_traffic_data()
    train_model("traffic", X, y)

def main():
    grid_X, grid_y = make_grid_data()
    traffic_X, traffic_y = make_traffic_data()
    aqi_X, aqi_y = make_aqi_data()

    train_model("grid", grid_X, grid_y)
    train_model("traffic", traffic_X, traffic_y)
    train_model("aqi", aqi_X, aqi_y)

if __name__ == "__main__":
    main()