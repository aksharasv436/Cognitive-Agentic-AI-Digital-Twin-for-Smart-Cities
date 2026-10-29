import asyncio
import math
from typing import List

import numpy as np
from starlette.concurrency import run_in_threadpool

from backend.app.core.config import SECTORS, SIM_TICK_SECONDS
from backend.app.schemas.telemetry import TelemetryPayload
from backend.app.services.twin import process_telemetry
from backend.app.services.ws_manager import broadcast_all


PROFILES = {
    "Sector_A1": (480, 1.5, 1.15),
    "Sector_A2": (320, 0.0, 1.0),
    "Sector_B1": (260, -0.5, 0.9),
    "Sector_B2": (400, 1.0, 1.1),
    "Sector_C1": (220, -1.0, 0.8),
    "Sector_C2": (300, 0.5, 1.0),
}

EFFECTS = {
    "heatwave": {"temperature": 9},
    "accident": {"traffic_density": 35, "aqi": 15},
    "stadium_event": {"occupancy": 220, "traffic_density": 20},
    "power_outage": {},
    "wildfire_smoke": {"aqi": 85},
}

CITY_WIDE = {"heatwave", "wildfire_smoke"}
VALID_SCENARIOS = {"clear", *EFFECTS.keys()}


def clamp(value, low, high):
    return max(low, min(float(value), high))


class Simulator:
    def __init__(self):
        self.running = True
        self.speed = 1.0
        self.sim_minutes = 8 * 60.0
        self.scenarios = []
        self.hold = {}
        self.prev = {}
        self.rng = np.random.default_rng()

    def add_scenario(self, name, sector_id, ticks):
        if name not in VALID_SCENARIOS:
            raise ValueError(f"Unknown simulation scenario: {name}")

        if name == "clear":
            self.scenarios = []
            return None

        if ticks < 1:
            raise ValueError("Scenario ticks must be at least 1")

        if sector_id is not None and sector_id not in SECTORS:
            raise ValueError(f"Unknown sector: {sector_id}")

        if name in CITY_WIDE:
            sector_id = None
        elif sector_id is None:
            sector_id = str(self.rng.choice(SECTORS))

        self.scenarios.append({
            "name": name,
            "sector_id": sector_id,
            "remaining": ticks,
        })
        return sector_id

    def hold_sector(self, sector_id: str, ticks: int = 4):
        if sector_id not in SECTORS:
            raise ValueError(f"Unknown sector: {sector_id}")
        self.hold[sector_id] = max(0, int(ticks))

    def state(self):
        day = int(self.sim_minutes // 1440)
        minute = int(self.sim_minutes % 1440)

        return {
            "running": self.running,
            "speed": self.speed,
            "clock": f"Day {day + 1} {minute // 60:02d}:{minute % 60:02d}",
            "scenarios": [dict(s) for s in self.scenarios],
        }

    def _target(self, sec, h, weekend):
        peak_occ, temperature_offset, traffic_multiplier = PROFILES[sec]

        def bell(center, width):
            return math.exp(-((h - center) ** 2) / (2 * width * width))

        morning_rush = bell(8.5, 1.6)
        evening_rush = bell(17.5, 1.8)

        temperature = (
            25
            + 2.2 * math.sin(2 * math.pi * (h - 9) / 24)
            + temperature_offset
        )

        occupancy = (
            peak_occ
            * (0.15 + 0.85 * bell(13, 3.5))
            * (0.75 if weekend else 1.0)
        )

        traffic = (
            18 + 18 * morning_rush + 17 * evening_rush
        ) * traffic_multiplier * (0.78 if weekend else 1.0)

        traffic = clamp(traffic, 10, 60)

        aqi = 30 + 0.5 * traffic + 1.5 * max(temperature - 28, 0)

        return {
            "temperature": temperature,
            "occupancy": occupancy,
            "traffic_density": traffic,
            "aqi": aqi,
        }

    def _apply_scenarios(self, inputs, sector_id):
        data = dict(inputs)

        for scenario in self.scenarios:
            if scenario["sector_id"] not in (None, sector_id):
                continue

            effects = EFFECTS[scenario["name"]]

            for key, amount in effects.items():
                data[key] += amount

        return data

    def step(self) -> List[TelemetryPayload]:
        self.sim_minutes += 10 * self.speed
        hour = (self.sim_minutes / 60) % 24
        is_weekend = (
            1 if int(self.sim_minutes // 1440) % 7 in (5, 6) else 0
        )

        out = []

        for sector_id in SECTORS:
            if self.hold.get(sector_id, 0) > 0:
                self.hold[sector_id] -= 1
                continue

            inputs = self._target(sector_id, hour, is_weekend)

            inputs = self._apply_scenarios(inputs, sector_id)

            inputs["temperature"] += self.rng.normal(0, 0.5)
            inputs["occupancy"] += self.rng.normal(0, 10)
            inputs["traffic_density"] += self.rng.normal(0, 3)
            inputs["aqi"] += self.rng.normal(0, 4)

            previous = self.prev.get(sector_id, inputs)
            current = {
                key: 0.5 * previous[key] + 0.5 * inputs[key]
                for key in inputs
            }
            self.prev[sector_id] = current

            out.append(
                TelemetryPayload(
                    sector_id=sector_id,
                    hour=int(hour),
                    is_weekend=is_weekend,
                    temperature=float(
                        np.clip(current["temperature"], 15, 45)
                    ),
                    occupancy=int(
                        np.clip(current["occupancy"], 0, 5000)
                    ),
                    traffic_density=int(
                        np.clip(current["traffic_density"], 0, 100)
                    ),
                    aqi=int(
                        np.clip(current["aqi"], 0, 500)
                    ),
                )
            )

        for scenario in self.scenarios:
            scenario["remaining"] -= 1

        self.scenarios = [
            scenario
            for scenario in self.scenarios
            if scenario["remaining"] > 0
        ]

        return out

    async def run(self):
        while True:
            await asyncio.sleep(SIM_TICK_SECONDS)

            if not self.running:
                continue

            try:
                items = self.step()

                if items:
                    views, events, stats, incidents = await run_in_threadpool(
                        process_telemetry, items
                    )
                    await broadcast_all(
                        views,
                        events,
                        stats,
                        incidents,
                        self.state(),
                    )

            except asyncio.CancelledError:
                raise
            except Exception as error:
                print("Simulator tick failed:", repr(error))


simulator = Simulator()