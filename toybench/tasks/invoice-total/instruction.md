# Invoice total

`invoice.csv` lists the line items of an invoice, with columns `item,quantity,unit_price`. Compute the amount due:

- subtotal = the sum of quantity × unit_price over all rows;
- tax = 8.25% of the subtotal, rounded to the nearest cent (exact halves round up);
- total = subtotal + tax.

Print exactly one line to standard output, in the form `Total: $1,234.56`: the word `Total:`, one space, a dollar sign, and the total with a comma as the thousands separator and exactly two decimal places. Print nothing else.
