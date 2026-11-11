def future_value(principal, annual_rate, years, periods_per_year):
    rate = annual_rate / 100.0
    n = periods_per_year
    value = principal * (1 + rate / n) ** (n * years)
    return round(value, 2)
