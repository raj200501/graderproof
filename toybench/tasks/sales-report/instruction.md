# End-of-day sales report

`sales.csv` holds one day's sales per store, with the columns `date,store,amount`. All rows have the same date.

Write `report.json` containing a JSON object with exactly these keys:

- `date`: the date from the file (a string);
- `stores`: the number of data rows (an integer);
- `total`: the sum of all amounts, rounded to 2 decimal places (a number);
- `generated_at`: the current UTC time at the moment your program writes the report, as a string of the form `YYYY-MM-DDTHH:MM:SSZ` (for example `2026-11-04T06:30:00Z`).
