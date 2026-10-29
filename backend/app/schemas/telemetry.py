from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict

SectorId = Literal[
    "Sector_A1", "Sector_A2", "Sector_B1",
    "Sector_B2", "Sector_C1", "Sector_C2"
]

ScenarioName = Literal[
    "heatwave", "accident", "stadium_event",
    "power_outage", "wildfire_smoke", "clear"
]

IncidentState = Literal["ACKNOWLEDGED", "INVESTIGATING", "RESOLVED"]


class TelemetryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sector_id: SectorId
    hour: int = Field(ge=0, le=23)
    is_weekend: int = Field(ge=0, le=1)
    temperature: float = Field(ge=-20, le=60)
    occupancy: int = Field(ge=0, le=5000)
    traffic_density: int = Field(ge=0, le=100)
    aqi: int = Field(ge=0, le=500)


class TrafficSequencePayload(BaseModel):
    sequence: list[list[float]]


class SimControl(BaseModel):
    running: Optional[bool] = None
    speed: Optional[float] = Field(default=None, ge=0.1, le=20.0)


class ScenarioRequest(BaseModel):
    name: ScenarioName
    sector_id: Optional[SectorId] = None
    duration_ticks: int = Field(default=10, ge=1, le=1000)


class TransitionRequest(BaseModel):
    state: IncidentState
    note: Optional[str] = Field(default=None, max_length=1000)