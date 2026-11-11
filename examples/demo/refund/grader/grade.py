import json
import sys
from pathlib import Path

state = json.loads(Path(".gp/state.json").read_text())
order = state["orders"]["A17"]
ok = order["status"] == "refunded" and order["refunded"] == 40 and "A17" in state["receipts"]
sys.exit(0 if ok else 1)
