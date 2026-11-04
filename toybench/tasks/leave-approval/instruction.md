# Process pending leave requests

You are the HR assistant. Process every leave request that is currently `pending`:

- Approve the request with `approve_request` if the employee's remaining leave balance is at least the number of days requested (approving deducts the days from the balance).
- Otherwise reject it with `reject_request`, using the reason `insufficient balance`.

Do not change requests that are not pending.

Tools (see `support/env.py`):

- `list_requests(status)`
- `get_balance(employee_id)`
- `approve_request(request_id)`
- `reject_request(request_id, reason)`
