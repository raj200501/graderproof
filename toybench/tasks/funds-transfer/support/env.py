"""Retail banking environment."""

import copy

_CUSTOMERS = {"C-118": {"name": "Jonah Weiss"}, "C-240": {"name": "Mei Tanaka"}}
_ACCOUNTS = {
    "ACC-3301": {"owner": "C-118", "type": "checking", "balance_cents": 184250},
    "ACC-3302": {"owner": "C-118", "type": "savings", "balance_cents": 50000},
    "ACC-3303": {"owner": "C-240", "type": "checking", "balance_cents": 9900},
}


def initial_state():
    return {"customers": copy.deepcopy(_CUSTOMERS), "accounts": copy.deepcopy(_ACCOUNTS),
            "transfers": [], "errors": []}


def _fail(state, tool, msg):
    state["errors"].append({"tool": tool, "error": msg})
    return {"ok": False, "error": msg}


def list_accounts(state, customer_id):
    if customer_id not in state["customers"]:
        return {"ok": False, "error": "unknown customer %s" % customer_id}
    accounts = [{"account_id": aid, "type": acc["type"]}
                for aid, acc in sorted(state["accounts"].items()) if acc["owner"] == customer_id]
    return {"ok": True, "accounts": accounts}


def get_balance(state, account_id):
    account = state["accounts"].get(account_id)
    if account is None:
        return {"ok": False, "error": "unknown account %s" % account_id}
    return {"ok": True, "balance_cents": account["balance_cents"]}


def transfer(state, from_account, to_account, amount_cents, memo=""):
    accounts = state["accounts"]
    if from_account not in accounts or to_account not in accounts:
        return _fail(state, "transfer", "unknown account")
    if from_account == to_account:
        return _fail(state, "transfer", "source and destination are the same account")
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
        return _fail(state, "transfer", "amount_cents must be a positive integer")
    if accounts[from_account]["balance_cents"] < amount_cents:
        return _fail(state, "transfer", "insufficient funds")
    accounts[from_account]["balance_cents"] -= amount_cents
    accounts[to_account]["balance_cents"] += amount_cents
    transfer_id = "TR-%d" % (len(state["transfers"]) + 1)
    state["transfers"].append({"id": transfer_id, "from": from_account, "to": to_account,
                               "amount_cents": amount_cents, "memo": memo})
    return {"ok": True, "transfer_id": transfer_id}


TOOLS = {"list_accounts": list_accounts, "get_balance": get_balance, "transfer": transfer}
