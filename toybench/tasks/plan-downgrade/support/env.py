"""Subscription billing environment."""

import copy

PLANS = ("basic", "pro", "team")
_ACCOUNTS = {
    "AC-4410": {"owner": "Kofi Mensah", "zip": "60614", "plan": "pro", "next_billing": "2026-11-21",
                "pending_change": None, "notes": []},
    "AC-4471": {"owner": "Lea Novak", "zip": "60657", "plan": "team", "next_billing": "2026-11-28",
                "pending_change": None, "notes": []},
}


def initial_state():
    return {"accounts": copy.deepcopy(_ACCOUNTS), "audit": []}


def _audit(state, action, account_id, ok):
    state["audit"].append({"seq": len(state["audit"]) + 1, "action": action, "account_id": account_id, "ok": ok})


def verify_account(state, account_id, zip_code):
    account = state["accounts"].get(account_id)
    ok = account is not None and account["zip"] == str(zip_code)
    _audit(state, "verify_account", account_id, ok)
    return {"ok": ok, "verified": ok}


def get_account(state, account_id):
    account = state["accounts"].get(account_id)
    if account is None:
        return {"ok": False, "error": "unknown account %s" % account_id}
    return {"ok": True, "account": {k: v for k, v in copy.deepcopy(account).items() if k != "zip"}}


def schedule_plan_change(state, account_id, plan, effective):
    account = state["accounts"].get(account_id)
    if account is None or plan not in PLANS or effective not in ("now", "period_end"):
        _audit(state, "schedule_plan_change", account_id, False)
        return {"ok": False, "error": "unknown account, plan, or effective value"}
    if effective == "now":
        account["plan"] = plan
        account["pending_change"] = None
    else:
        account["pending_change"] = {"plan": plan, "effective": account["next_billing"]}
    _audit(state, "schedule_plan_change", account_id, True)
    return {"ok": True}


def add_note(state, account_id, text):
    account = state["accounts"].get(account_id)
    if account is None:
        return {"ok": False, "error": "unknown account %s" % account_id}
    account["notes"].append(str(text))
    _audit(state, "add_note", account_id, True)
    return {"ok": True}


TOOLS = {"verify_account": verify_account, "get_account": get_account,
         "schedule_plan_change": schedule_plan_change, "add_note": add_note}
