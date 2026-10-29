from pydantic import BaseModel
from typing import Dict

class MultiDomainPredictionOutput(BaseModel):
    sector_id: str
    domain: str
    is_anomaly: bool
    risk_score: float
    severity: str
    status: str
    action: str

class AnalyticsOutput(BaseModel):
    total_scans: int
    total_anomalies: int
    anomaly_rate_percent: float
    highest_risk_sector: str