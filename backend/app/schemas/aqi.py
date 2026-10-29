from pydantic import BaseModel

class AQITelemetryInput(BaseModel):
    sector_id: str
    pm2_5: float
    no2: float
    co2: float