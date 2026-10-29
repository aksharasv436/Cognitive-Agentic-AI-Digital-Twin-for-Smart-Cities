from collections.abc import Mapping
import numpy as np
from backend.app.core.config import COUPLING_MATRIX, DECAY, HOPS, SECTORS

CASCADE_GAIN = 0.35

def _weights():
    weights = np.asarray(COUPLING_MATRIX, dtype=float).copy()
    expected_shape = (len(SECTORS), len(SECTORS))
    if weights.shape != expected_shape:
        raise ValueError(
            f"COUPLING_MATRIX must have shape {expected_shape}, got {weights.shape}"
        )
    weights = np.clip(weights, 0.0, None)
    np.fill_diagonal(weights, 0.0)
    row_sums = weights.sum(axis=1, keepdims=True)
    weights = weights / np.maximum(row_sums, 1.0)
    return weights

def calculate_cascading_spillover(sector_id, direct_risk):
    if sector_id not in SECTORS:
        return {}
    risk = float(np.clip(direct_risk, 0.0, 1.0))
    weights = _weights()
    source_idx = SECTORS.index(sector_id)
    contributions = weights[source_idx] * risk * float(DECAY)
    return {
        SECTORS[i]: float(contributions[i])
        for i in range(len(SECTORS))
        if i != source_idx and contributions[i] > 0
    }

def effective_risk(direct_risks):
    was_mapping = isinstance(direct_risks, Mapping)

    if was_mapping:
        direct = np.array(
            [direct_risks.get(sector, 0.0) for sector in SECTORS],
            dtype=float,
        )
    else:
        direct = np.asarray(direct_risks, dtype=float).reshape(-1)

    if direct.size != len(SECTORS):
        raise ValueError(
            f"Expected {len(SECTORS)} direct risks, received {direct.size}"
        )

    direct = np.clip(np.nan_to_num(direct, nan=0.0), 0.0, 1.0)
    weights = _weights()
    frontier = direct.copy()
    spillover = np.zeros_like(direct)
    decay = float(np.clip(DECAY, 0.0, 1.0))

    for hop in range(max(0, int(HOPS))):
        frontier = (weights @ frontier) * decay
        frontier = np.clip(frontier, 0.0, 1.0)
        spillover = np.maximum(spillover, frontier)
    effective = direct + CASCADE_GAIN * spillover * (1.0 - direct)
    effective = np.clip(effective, 0.0, 1.0)

    if was_mapping:
        return {sector: float(effective[i]) for i, sector in enumerate(SECTORS)}
    return effective