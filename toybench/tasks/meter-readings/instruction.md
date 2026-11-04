# Monthly electricity usage

`readings.csv` contains the October meter readings for the office building, with the columns `meter,date,reading_kwh` (dates are ISO `YYYY-MM-DD`, readings are whole kWh, and each meter has at least two readings).

Write `usage.csv` with the header row `meter,kwh` followed by one row per meter that appears in `readings.csv`, sorted by meter ID. `kwh` is the meter's consumption for the month: its reading on the latest date minus its reading on the earliest date, as an integer.
