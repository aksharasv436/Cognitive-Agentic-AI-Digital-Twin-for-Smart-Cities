from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from backend.app.core import state
from backend.app.schemas.telemetry import (
    ScenarioRequest,
    SectorId,
    SimControl,
    TelemetryPayload,
    TrafficSequencePayload,
    TransitionRequest,
)
from backend.app.services import incidents as incident_service
from backend.app.services import twin
from backend.app.services.predictor import model_importances, models_ready
from backend.app.services.simulator import simulator
from backend.app.services.ws_manager import broadcast_all, manager

router = APIRouter()


def require_models():
    if not models_ready():
        raise HTTPException(
            status_code=503,
            detail="One or more ML models are not loaded.",
        )


@router.post("/predict")
async def predict_multi_hazard(payload: TelemetryPayload):
    require_models()
    simulator.hold_sector(payload.sector_id)

    views, events, stats, incidents = await run_in_threadpool(
        twin.process_telemetry, [payload]
    )

    await broadcast_all(
        views, events, stats, incidents, simulator.state()
    )

    return views[payload.sector_id]


@router.post("/whatif")
async def whatif(payload: TelemetryPayload):
    require_models()
    return await run_in_threadpool(twin.whatif, payload)


@router.post("/predict/traffic-raw")
def predict_raw_traffic_sequence(payload: TrafficSequencePayload):
    if "traffic" not in state.MODELS:
        raise HTTPException(
            status_code=503,
            detail="Traffic model not loaded.",
        )

    sequence = np.asarray(payload.sequence, dtype=float)

    if sequence.shape != (12, 207):
        raise HTTPException(
            status_code=400,
            detail=f"Expected input sequence shape (12, 207), got {sequence.shape}",
        )

    if not np.isfinite(sequence).all():
        raise HTTPException(
            status_code=400,
            detail="Sequence must contain only finite numbers.",
        )

    latest = sequence[-1]
    avg_speed = float(np.mean(latest))
    density = int(np.clip((1.0 - avg_speed / 70.0) * 100, 0, 100))

    frame = pd.DataFrame([{
        "hour": 12,
        "is_weekend": 0,
        "traffic_density": density,
    }])

    model = state.MODELS["traffic"]
    probabilities = model.predict_proba(frame)[0]
    classes = list(model.classes_)
    risk = (
        float(probabilities[classes.index(1)])
        if 1 in classes else 0.0
    )

    return {
        "average_speed_mph": round(avg_speed, 2),
        "calculated_traffic_density": density,
        "traffic_risk_score": round(risk, 4),
        "top_bottleneck_sensor_indices": np.argsort(latest)[:5].tolist(),
    }


@router.get("/history/{sector_id}")
def get_sector_history(
    sector_id: SectorId,
    limit: int = Query(default=100, ge=1, le=200),
):
    logs = state.telemetry_history[sector_id][-limit:]

    average_temperature = (
        round(sum(item["temperature"] for item in logs) / len(logs), 2)
        if logs else 0.0
    )

    return {
        "sector_id": sector_id,
        "logs_count": len(logs),
        "average_temperature": average_temperature,
        "history": logs,
    }


@router.get("/analytics")
def get_analytics():
    return twin.analytics_snapshot()


@router.get("/model-info")
def get_model_diagnostics():
    require_models()
    return model_importances()


@router.get("/incidents")
def list_incidents(status: Optional[str] = None):
    items = list(state.active_incidents.values())

    if status:
        status = status.upper()

        if status == "OPEN":
            items = incident_service.open_incidents()
        else:
            items = [
                incident for incident in items
                if incident["state"] == status
            ]

    return {"incidents": items}


@router.post("/incidents/{incident_id}/transition")
async def transition_incident(
    incident_id: str,
    body: TransitionRequest,
):
    try:
        incident = incident_service.transition(
            incident_id, body.state, body.note
        )
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail="Incident ID not found.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    await manager.broadcast({
        "type": "STATE",
        "data": {
            "analytics": twin.analytics_snapshot(),
            "incidents": incident_service.open_incidents(),
            "events": [],
            "sim": simulator.state(),
        },
    })

    return incident


@router.post("/incidents/resolve/{incident_id}")
async def resolve_incident(incident_id: str):
    return await transition_incident(
        incident_id,
        TransitionRequest(state="RESOLVED"),
    )


@router.get("/simulation")
def simulation_state():
    return simulator.state()


@router.post("/simulation/control")
def simulation_control(body: SimControl):
    if body.running is not None:
        simulator.running = body.running

    if body.speed is not None:
        simulator.speed = body.speed

    return simulator.state()


@router.post("/simulation/scenario")
def simulation_scenario(body: ScenarioRequest):
    sector = simulator.add_scenario(
        body.name,
        body.sector_id,
        body.duration_ticks,
    )

    return {
        "applied": body.name,
        "sector_id": sector or "city-wide",
        **simulator.state(),
    }
def simulation_scenario(body: ScenarioRequest):
    sector = simulator.add_scenario(body.name, body.sector_id, body.duration_ticks)
    return {"applied": body.name, "sector_id": sector or "city-wide", **simulator.state()}