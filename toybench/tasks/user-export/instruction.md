# Export users as JSON Lines

The CRM import job reads JSON Lines. Convert `users.csv` (columns `id,first_name,last_name,email,signup_date`) into `users.jsonl`: one JSON object per line, one line per CSV row, in the same order. Each object has exactly these keys:

- `id`: the id as an integer;
- `name`: the first name and last name separated by a single space;
- `email`: the email address converted to lowercase;
- `signup`: the signup date as `YYYY-MM-DD` (the CSV writes dates as `MM/DD/YYYY`).
