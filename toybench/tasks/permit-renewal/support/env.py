"""City parking permit environment."""

import copy

_CUSTOMERS = {"CU-5521": {"name": "Dana Kowalski", "card_last4": "0094"},
              "CU-6100": {"name": "Raul Mendes", "card_last4": "7781"}}
_PERMITS = {
    "PRM-7730": {"customer_id": "CU-5521", "plate": "KX-482-LM", "zone": "R4", "expires": "2026-11-30",
                 "status": "active"},
    "PRM-7731": {"customer_id": "CU-6100", "plate": "KX-713-AB", "zone": "R4", "expires": "2027-02-28",
                 "status": "active"},
}
_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def initial_state():
    return {"customers": copy.deepcopy(_CUSTOMERS), "permits": copy.deepcopy(_PERMITS),
            "charges": [], "call_log": []}


def _log(state, tool, ok, detail=""):
    state["call_log"].append({"tool": tool, "status": "ok" if ok else "error", "detail": detail})


def _add_months(iso, months):
    year, month, day = (int(part) for part in iso.split("-"))
    index = month - 1 + months
    year, month = year + index // 12, index % 12 + 1
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    last = 29 if month == 2 and leap else _DAYS[month - 1]
    return "%04d-%02d-%02d" % (year, month, min(day, last))


def lookup_permit(state, plate):
    for permit_id, permit in sorted(state["permits"].items()):
        if permit["plate"] == plate:
            return {"ok": True, "permit_id": permit_id, **copy.deepcopy(permit)}
    return {"ok": False, "error": "no permit for plate %s" % plate}


def renew_permit(state, permit_id, months):
    permit = state["permits"].get(permit_id)
    if permit is None or not isinstance(months, int) or isinstance(months, bool) or not 1 <= months <= 24:
        _log(state, "renew_permit", False, "bad permit or months")
        return {"ok": False, "error": "unknown permit or months not in 1..24"}
    permit["expires"] = _add_months(permit["expires"], months)
    _log(state, "renew_permit", True, permit_id)
    return {"ok": True, "expires": permit["expires"]}


def charge_card(state, customer_id, amount_cents, description):
    if customer_id not in state["customers"] or not isinstance(amount_cents, int) or amount_cents <= 0:
        _log(state, "charge_card", False, "bad customer or amount")
        return {"ok": False, "error": "unknown customer or invalid amount"}
    state["charges"].append({"customer_id": customer_id, "amount_cents": amount_cents,
                             "description": description})
    _log(state, "charge_card", True, customer_id)
    return {"ok": True, "charge_id": "CH-%d" % len(state["charges"])}


TOOLS = {"lookup_permit": lookup_permit, "renew_permit": renew_permit, "charge_card": charge_card}
