# Triage the shared inbox

In the finance team's shared inbox, apply the label `invoices` to every message whose sender is exactly `billing@northwind.example`, and archive each of those messages.

Do not label, archive, or otherwise change any other message, and do not remove existing labels.

Tools (see `support/env.py`):

- `list_messages()`
- `add_label(message_id, label)`
- `remove_label(message_id, label)`
- `archive(message_id)`
