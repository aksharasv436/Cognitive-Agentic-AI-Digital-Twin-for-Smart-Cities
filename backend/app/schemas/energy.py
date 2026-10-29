from pydantic import BaseModel

class EnergyTelemetryInput(BaseModel):
    sector_id: str
    hour: int
    is_weekend: int
    temperature: float
    occupancy: int