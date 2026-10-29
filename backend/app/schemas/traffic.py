from pydantic import BaseModel

class TrafficTelemetryInput(BaseModel):
    sector_id: str
    vehicle_count: int
    average_speed: float
    signal_delay_sec: int