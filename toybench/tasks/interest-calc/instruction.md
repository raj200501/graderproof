# Compound interest calculator

Write a Python module `finance.py` with a function `future_value(principal, annual_rate, years, periods_per_year)` for the savings calculator on the bank's website.

- `principal` is the amount deposited (a number of dollars), `annual_rate` is the nominal yearly interest rate in percent (so `4.5` means 4.5%), `years` is a whole number of years, and `periods_per_year` is how many times per year interest is compounded (for example 12 for monthly).
- The result is `principal * (1 + r / n) ** (n * years)`, where `r = annual_rate / 100` and `n = periods_per_year`.
- Return the result as a float rounded to the nearest cent (2 decimal places).
