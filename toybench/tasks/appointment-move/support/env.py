"""Clinic scheduling environment."""

import copy

_PATIENTS = {"P-3307": {"name": "Gareth Lowe", "mobile": "+44 7700 900412"},
             "P-4410": {"name": "Ines Duarte", "mobile": "+44 7700 900877"}}
_APPOINTMENTS = {
    "APT-6620": {"patient_id": "P-3307", "provider": "Dr. Hale", "date": "2026-11-11", "time": "09:00",
                 "status": "scheduled"},
    "APT-6655": {"patient_id": "P-4410", "provider": "Dr. Hale", "date": "2026-11-18", "time": "11:00",
                 "status": "scheduled"},
}
_OPEN = {"Dr. Hale": {"2026-11-18": ["09:30", "10:15", "14:00"], "2026-11-19": ["08:45"]}}


def initial_state():
    return {"patients": copy.deepcopy(_PATIENTS), "appointments": copy.deepcopy(_APPOINTMENTS),
            "open_slots": copy.deepcopy(_OPEN), "sms_outbox": []}


def find_slots(state, provider, date):
    return {"ok": True, "slots": list(state["open_slots"].get(provider, {}).get(date, []))}


def reschedule(state, appointment_id, date, time):
    appt = state["appointments"].get(appointment_id)
    if appt is None:
        return {"ok": False, "error": "unknown appointment %s" % appointment_id}
    slots = state["open_slots"].setdefault(appt["provider"], {})
    if time not in slots.get(date, []):
        return {"ok": False, "error": "%s %s is not an open slot" % (date, time)}
    slots[date].remove(time)
    slots.setdefault(appt["date"], []).append(appt["time"])
    slots[appt["date"]].sort()
    appt["date"], appt["time"] = date, time
    return {"ok": True}


def send_sms(state, patient_id, text):
    if patient_id not in state["patients"]:
        return {"ok": False, "error": "unknown patient %s" % patient_id}
    state["sms_outbox"].append({"patient_id": patient_id, "text": str(text)})
    return {"ok": True}


TOOLS = {"find_slots": find_slots, "reschedule": reschedule, "send_sms": send_sms}
