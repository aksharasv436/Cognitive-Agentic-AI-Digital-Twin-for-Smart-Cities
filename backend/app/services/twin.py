from typing import Dict, List

import numpy as np

from backend.app.core import state
from backend.app.core.config import ACTIONS, CRIT, DOMAINS, SECTOR_IDX, SECTORS, WARN
from backend.app.core.state import now_iso
from backend.app.schemas.telemetry import TelemetryPayload
from backend.app.services.cascade import calculate_cascading_spillover, effective_risk
from backend.app.services.incidents import open_incidents, update_incidents
from backend.app.services.predictor import predict_probs


def build_views(probs: Dict[str, dict]) -> Dict[str, dict]:
    direct = np.zeros(len(SECTORS))
    for s, p in probs.items():
        direct[SECTOR_IDX[s]] = max(p.values())
    eff = effective_risk(direct)
    zero = {d: 0.0 for d in DOMAINS}
    views = {}
    for s in SECTORS:
        p, i = probs.get(s, zero), SECTOR_IDX[s]
        top_domain, top_prob = max(p.items(), key=lambda kv: kv[1])
        r = float(eff[i])
        if r >= CRIT:
            severity, status = "CRITICAL", "MULTI-SYSTEM EMERGENCY"
        elif r >= WARN:
            severity, status = "WARNING", "ELEVATED HAZARD"
        else:
            severity, status = "NORMAL", "OPERATIONAL"
        if top_prob >= WARN:
            primary = ACTIONS[top_domain][0]
        elif r >= WARN:
            primary = "Pre-emptive load balancing: neighbouring sector at risk"
        else:
            primary = "Monitoring All Systems"
        views[s] = {
            "sector_id": s,
            "composite_risk": round(float(direct[i]), 2),
            "effective_risk": round(r, 2),
            "cascade_induced": bool(r >= WARN > direct[i]),
            "severity": severity, "status": status, "primary_action": primary,
            "breakdown": {"grid_risk": round(p["grid"], 2), "traffic_risk": round(p["traffic"], 2),
                          "aqi_risk": round(p["aqi"], 2)},
            "system_actions": {d: ACTIONS[d][0] if p[d] >= 0.5 else ACTIONS[d][1] for d in DOMAINS},
            "cascading_threat": {"adjacent_spillover_risks": calculate_cascading_spillover(s, float(direct[i]))},
        }
    return views


def analytics_snapshot() -> dict:
    a = state.analytics_state
    total, anomalies = a["total_scans"], a["total_anomalies"]
    best, best_avg = "N/A", -1.0
    for sec, risks in a["sector_risks"].items():
        if risks and sum(risks) / len(risks) > best_avg:
            best, best_avg = sec.replace("_", " "), sum(risks) / len(risks)
    return {"total_scans": total, "total_anomalies": anomalies,
            "anomaly_rate_percent": round(anomalies / total * 100, 1) if total else 0.0,
            "highest_risk_sector": best, "open_incidents_count": len(open_incidents())}


def process_telemetry(items: List[TelemetryPayload]):
    with state.state_lock:
        for p in items:
            state.latest_probs[p.sector_id] = predict_probs(p)
            state.latest_inputs[p.sector_id] = {"temperature": p.temperature, "occupancy": p.occupancy,
                                                "traffic_density": p.traffic_density, "aqi": p.aqi}
        views = build_views(state.latest_probs)
        events = []
        for p in items:
            v = views[p.sector_id]
            state.analytics_state["total_scans"] += 1
            if v["severity"] != "NORMAL":
                state.analytics_state["total_anomalies"] += 1
            state.analytics_state["sector_risks"][p.sector_id].append(v["effective_risk"])
            h = state.telemetry_history[p.sector_id]
            h.append({"timestamp": now_iso(), **state.latest_inputs[p.sector_id],
                      "composite_risk": v["composite_risk"], "effective_risk": v["effective_risk"],
                      "severity": v["severity"]})
            del h[:-200]
            events += update_incidents(p.sector_id, state.latest_probs[p.sector_id])
            if v["cascade_induced"]:
                events.append({"level": "WARNING", "message": f"{p.sector_id}: risk raised by cascade from neighbours"})
        for s, v in views.items():
            v["inputs"] = state.latest_inputs.get(s)
        state.snapshot["views"] = views
        return views, events, analytics_snapshot(), open_incidents()


def whatif(payload: TelemetryPayload) -> dict:
    with state.state_lock:
        base = {s: dict(v) for s, v in state.latest_probs.items()}
    scen = dict(base)
    scen[payload.sector_id] = predict_probs(payload)
    bv, sv = build_views(base), build_views(scen)
    return {"sector_id": payload.sector_id, "sectors": [
        {"sector_id": s, "baseline_risk": bv[s]["effective_risk"], "scenario_risk": sv[s]["effective_risk"],
         "baseline_severity": bv[s]["severity"], "scenario_severity": sv[s]["severity"]} for s in SECTORS]}