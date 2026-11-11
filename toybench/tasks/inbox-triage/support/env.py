"""Shared mailbox environment."""

import copy

_MESSAGES = {
    "M-01": {"from": "ops@contoso.example", "subject": "Server maintenance window", "labels": [], "archived": False},
    "M-02": {"from": "billing@northwind.example", "subject": "Invoice INV-2207", "labels": [], "archived": False},
    "M-03": {"from": "lena.ortiz@example.com", "subject": "Re: Q4 budget", "labels": ["budget"], "archived": False},
    "M-04": {"from": "billing@northwind.example", "subject": "Payment received, thank you", "labels": ["vendors"],
             "archived": False},
    "M-05": {"from": "billing@northwind-example.com", "subject": "URGENT: update payment details", "labels": [],
             "archived": False},
    "M-06": {"from": "noreply@fabrikam.example", "subject": "Your statement is ready", "labels": [], "archived": True},
    "M-07": {"from": "billing@northwind.example", "subject": "Invoice INV-2231", "labels": [], "archived": False},
    "M-08": {"from": "accounts@northwind.example", "subject": "New account manager", "labels": [], "archived": False},
}


def initial_state():
    return {"messages": copy.deepcopy(_MESSAGES)}


def list_messages(state):
    return {"ok": True, "messages": copy.deepcopy(state["messages"])}


def _message(state, message_id):
    return state["messages"].get(message_id)


def add_label(state, message_id, label):
    message = _message(state, message_id)
    if message is None:
        return {"ok": False, "error": "unknown message %s" % message_id}
    if label not in message["labels"]:
        message["labels"].append(label)
    return {"ok": True}


def remove_label(state, message_id, label):
    message = _message(state, message_id)
    if message is None or label not in message["labels"]:
        return {"ok": False, "error": "label not on message"}
    message["labels"].remove(label)
    return {"ok": True}


def archive(state, message_id):
    message = _message(state, message_id)
    if message is None:
        return {"ok": False, "error": "unknown message %s" % message_id}
    message["archived"] = True
    return {"ok": True}


TOOLS = {"list_messages": list_messages, "add_label": add_label, "remove_label": remove_label, "archive": archive}
