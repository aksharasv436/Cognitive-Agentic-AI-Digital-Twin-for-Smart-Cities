import threading
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional
 
from backend.app.core.config import SECTORS
 
MODELS: dict = {}
state_lock = threading.RLock()
 
latest_probs: Dict[str, dict] = {}
latest_inputs: Dict[str, dict] = {}
snapshot: Dict[str, Optional[dict]] = {"views": None}
 
analytics_state = {"total_scans": 0, "total_anomalies": 0,
                   "sector_risks": {s: deque(maxlen=200) for s in SECTORS}}
telemetry_history: Dict[str, List[dict]] = {s: [] for s in SECTORS}
active_incidents: Dict[str, dict] = {}
 
 
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
