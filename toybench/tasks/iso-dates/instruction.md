# Normalize dates from supplier invoices

Supplier invoices write dates in different ways. Write a Python module `dateparse.py` with a function `to_iso_date(text)` that returns the date as an ISO string `YYYY-MM-DD`.

Accepted input formats (surrounding spaces are ignored):

- `Month D, YYYY`, where Month is an English month name, either in full (`March`) or as its three-letter abbreviation (`Mar`), in any capitalization, and D has one or two digits: `"March 5, 2026"` gives `"2026-03-05"`.
- `DD/MM/YYYY` (day first, two digits each): `"05/03/2026"` gives `"2026-03-05"`.
- `YYYY.MM.DD`: `"2026.03.05"` gives `"2026-03-05"`.

Raise `ValueError` for anything else, including dates that do not exist such as `"31/04/2026"`.
