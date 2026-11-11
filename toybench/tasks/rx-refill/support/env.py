"""Pharmacy refill environment."""

import copy

_PRESCRIPTIONS = {
    "RX-1001": {"patient_id": "P-5512", "drug": "atorvastatin 20 mg", "refills_left": 2},
    "RX-1002": {"patient_id": "P-5512", "drug": "amoxicillin 500 mg", "refills_left": 0},
    "RX-1107": {"patient_id": "P-6020", "drug": "atorvastatin 40 mg", "refills_left": 5},
}
_PHARMACIES = {"PH-ELM": "Elm Street Pharmacy", "PH-HBR": "Harbour Road Pharmacy"}


def initial_state():
    return {"prescriptions": copy.deepcopy(_PRESCRIPTIONS), "pharmacies": dict(_PHARMACIES), "refills": [],
            "notifications": [], "events": []}


def _event(state, kind, **fields):
    state["events"].append(dict(seq=len(state["events"]) + 1, kind=kind, **fields))


def list_prescriptions(state, patient_id):
    return {"ok": True, "prescriptions": {rx: copy.deepcopy(p) for rx, p in state["prescriptions"].items()
                                          if p["patient_id"] == patient_id}}


def list_pharmacies(state):
    return {"ok": True, "pharmacies": dict(state["pharmacies"])}


def request_refill(state, rx_id, pharmacy_id):
    rx = state["prescriptions"].get(rx_id)
    if rx is None or pharmacy_id not in state["pharmacies"]:
        return {"ok": False, "error": "unknown prescription or pharmacy"}
    if rx["refills_left"] <= 0:
        return {"ok": False, "error": "no refills left; the prescriber must renew it"}
    rx["refills_left"] -= 1
    state["refills"].append({"rx_id": rx_id, "pharmacy_id": pharmacy_id})
    _event(state, "refill", rx_id=rx_id)
    return {"ok": True, "ready": "tomorrow after 14:00"}


def notify_patient(state, patient_id, message):
    state["notifications"].append({"patient_id": patient_id, "message": str(message)})
    _event(state, "notify", patient_id=patient_id)
    return {"ok": True}


TOOLS = {"list_prescriptions": list_prescriptions, "list_pharmacies": list_pharmacies,
         "request_refill": request_refill, "notify_patient": notify_patient}
