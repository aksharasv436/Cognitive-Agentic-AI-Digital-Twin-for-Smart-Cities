import joblib
import numpy as np
import pandas as pd

from backend.app.core import state
from backend.app.core.config import FEATURES, MODEL_PATHS, DOMAINS


def load_models():
    state.MODELS.clear()

    for domain in DOMAINS:
        path = MODEL_PATHS[domain]

        try:
            model = joblib.load(path)

            if not hasattr(model, "predict_proba"):
                raise TypeError(
                    f"{domain} model must implement predict_proba()."
                )

            state.MODELS[domain] = model
            print(f"Loaded {domain} model from {path}")

        except FileNotFoundError:
            print(f"Model file missing: {path}")

        except Exception as exc:
            print(f"Failed to load {domain} model: {exc}")


def models_ready() -> bool:
    return all(domain in state.MODELS for domain in DOMAINS)


def _positive_probability(model, features: pd.DataFrame) -> float:
    probabilities = model.predict_proba(features)[0]
    classes = list(model.classes_)

    if 1 in classes:
        return float(probabilities[classes.index(1)])

    return 0.0


def predict_probs(payload) -> dict:
    hour = int(payload.hour)
    weekend = int(payload.is_weekend)
    temperature = float(payload.temperature)
    occupancy = int(payload.occupancy)
    traffic_density = int(payload.traffic_density)
    aqi = int(payload.aqi)

    inputs = {
        "grid": {
            "hour": hour,
            "is_weekend": weekend,
            "temperature": temperature,
            "occupancy": occupancy,
        },
        "traffic": {
            "hour": hour,
            "is_weekend": weekend,
            "traffic_density": traffic_density,
        },
        "aqi": {
            "temperature": temperature,
            "traffic_density": traffic_density,
            "aqi": aqi,
        },
    }

    result = {}

    for domain in DOMAINS:
        model = state.MODELS.get(domain)

        if model is None:
            raise RuntimeError(f"{domain} model is not loaded.")

        frame = pd.DataFrame(
            [inputs[domain]],
            columns=FEATURES[domain],
        )

        result[domain] = round(
            float(np.clip(_positive_probability(model, frame), 0.0, 1.0)),
            4,
        )

    return result


def model_importances() -> dict:
    if not models_ready():
        raise RuntimeError("One or more models are not loaded.")

    diagnostics = {}

    for domain in DOMAINS:
        model = state.MODELS[domain]
        importances = getattr(model, "feature_importances_", None)

        diagnostics[domain] = {
            "model_type": type(model).__name__,
            "features": FEATURES[domain],
            "feature_importances": (
                {
                    name: round(float(value), 4)
                    for name, value in zip(FEATURES[domain], importances)
                }
                if importances is not None
                else {}
            ),
            "classes": [str(value) for value in model.classes_],
        }

    return diagnostics