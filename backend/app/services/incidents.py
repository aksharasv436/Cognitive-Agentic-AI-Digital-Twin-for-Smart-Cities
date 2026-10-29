from uuid import uuid4

from backend.app.core import state
from backend.app.core.config import AUTO_RESOLVE_AFTER, CRIT, DOMAINS, WARN
from backend.app.core.state import now_iso

ALLOWED_TRANSITIONS = {
    "OPEN": {"ACKNOWLEDGED", "INVESTIGATING", "RESOLVED"},
    "ACKNOWLEDGED": {"INVESTIGATING", "RESOLVED"},
    "INVESTIGATING": {"ACKNOWLEDGED", "RESOLVED"},
    "RESOLVED": set(),
}


def open_incidents() -> list:
    with state.state_lock:
        return [
            dict(incident)
            for incident in state.active_incidents.values()
            if incident["state"] != "RESOLVED"
        ]


def update_incidents(sector_id: str, probabilities: dict) -> list:
    events = []

    for domain in DOMAINS:
        probability = float(probabilities.get(domain, 0.0))
        incident_key = f"{sector_id}:{domain}"
        incident = state.active_incidents.get(incident_key)

        if probability >= WARN:
            severity = "CRITICAL" if probability >= CRIT else "WARNING"

            if incident is None or incident["state"] == "RESOLVED":
                incident = {
                    "id": str(uuid4()),
                    "key": incident_key,
                    "sector_id": sector_id,
                    "domain": domain,
                    "state": "OPEN",
                    "severity": severity,
                    "risk_score": round(probability, 4),
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "resolved_at": None,
                    "notes": [],
                    "safe_ticks": 0,
                }
                state.active_incidents[incident_key] = incident

                events.append({
                    "level": severity,
                    "message": (
                        f"{severity} {domain} risk detected in {sector_id}"
                    ),
                    "incident_id": incident["id"],
                })
            else:
                incident["risk_score"] = round(probability, 4)
                incident["severity"] = severity
                incident["updated_at"] = now_iso()
                incident["safe_ticks"] = 0

            continue

        if incident is None or incident["state"] == "RESOLVED":
            continue

        incident["safe_ticks"] += 1
        incident["updated_at"] = now_iso()

        if incident["safe_ticks"] >= AUTO_RESOLVE_AFTER:
            incident["state"] = "RESOLVED"
            incident["resolved_at"] = now_iso()
            incident["notes"].append({
                "timestamp": now_iso(),
                "note": "Automatically resolved after consecutive safe readings.",
            })

            events.append({
                "level": "INFO",
                "message": (
                    f"{domain} incident automatically resolved in {sector_id}"
                ),
                "incident_id": incident["id"],
            })

    return events


def transition(incident_id: str, new_state: str, note: str = None) -> dict:
    target = None

    with state.state_lock:
        for incident in state.active_incidents.values():
            if incident["id"] == incident_id:
                target = incident
                break

        if target is None:
            raise KeyError(incident_id)

        new_state = new_state.upper()
        current = target["state"]

        if new_state not in ALLOWED_TRANSITIONS.get(current, set()):
            raise ValueError(
                f"Cannot transition incident from {current} to {new_state}."
            )

        target["state"] = new_state
        target["updated_at"] = now_iso()

        if new_state == "RESOLVED":
            target["resolved_at"] = now_iso()

        if note:
            target["notes"].append({
                "timestamp": now_iso(),
                "note": note,
            })

        return dict(target)