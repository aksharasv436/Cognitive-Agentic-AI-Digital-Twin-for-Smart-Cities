import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.router import router
from backend.app.core import state
from backend.app.core.config import ALLOWED_ORIGINS
from backend.app.services.incidents import open_incidents
from backend.app.services.predictor import load_models, models_ready
from backend.app.services.simulator import simulator
from backend.app.services.twin import analytics_snapshot
from backend.app.services.ws_manager import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_models()
    task = asyncio.create_task(simulator.run()) if models_ready() else None
    if task is None:
        print("WARNING: models missing, simulator not started.")
    yield
    if task:
        task.cancel()


app = FastAPI(title="Smart City Multi-Model Digital Twin API", version="3.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "models_loaded": sorted(state.MODELS), "simulator_running": simulator.running}


@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        views = state.snapshot["views"]
        if views:                              
            for v in views.values():
                await websocket.send_json({"type": "TELEMETRY_UPDATE", "data": v})
            await websocket.send_json({"type": "STATE", "data": {
                "analytics": analytics_snapshot(), "incidents": open_incidents(), "events": [],
                "sim": simulator.state()}})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)