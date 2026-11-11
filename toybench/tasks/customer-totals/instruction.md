# Payments per customer

`payments.csv` lists October payments with the columns `date,customer,amount`.

Write `totals.csv`: a CSV file with the header row `customer,total` followed by one row per customer, giving the sum of that customer's payments. Sort the rows by customer name (plain string comparison) and write each total with exactly two decimal places (for example `600.00`). Customer names are CSV values and must be quoted where the CSV format requires it.
