# Expense report by category

`expenses.csv` lists the team's October expenses with the columns `date,category,amount`. Produce two files:

- `by_category.csv`: the header row `category,total`, then one row per category that occurs in `expenses.csv`, sorted by category name, where `total` is the sum of that category's amounts written with exactly two decimal places.
- `summary.json`: a JSON object with exactly two keys, `categories` (the number of categories, an integer) and `grand_total` (the sum of all amounts, rounded to 2 decimal places, as a number).
