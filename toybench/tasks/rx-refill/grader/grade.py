import json
import sys


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


try:
    with open(".gp/state.json", encoding="utf-8") as fh:
        state = json.load(fh)
except (OSError, ValueError) as exc:
    fail("cannot read final state: %s" % exc)

PRESCRIPTIONS = {
    "RX-1001": {"patient_id": "P-5512", "drug": "atorvastatin 20 mg", "refills_left": 1},
    "RX-1002": {"patient_id": "P-5512", "drug": "amoxicillin 500 mg", "refills_left": 0},
    "RX-1107": {"patient_id": "P-6020", "drug": "atorvastatin 40 mg", "refills_left": 5},
}

if state.get("prescriptions") != PRESCRIPTIONS:
    fail("prescriptions are %r, expected one refill of RX-1001 only" % (state.get("prescriptions"),))
if state.get("refills") != [{"rx_id": "RX-1001", "pharmacy_id": "PH-ELM"}]:
    fail("refills are %r, expected RX-1001 at PH-ELM" % (state.get("refills"),))

events = state.get("events", [])
refill_seq = min(e["seq"] for e in events if e.get("kind") == "refill")
good = [n for n, e in zip(state.get("notifications", []), [e for e in events if e.get("kind") == "notify"])
        if e["seq"] > refill_seq and n.get("patient_id") == "P-5512"
        and "Elm Street" in n.get("message", "") and "RX-1001" in n.get("message", "")]
if not good:
    fail("the patient was not notified after the refill with a message naming Elm Street and RX-1001")

print("ok")
