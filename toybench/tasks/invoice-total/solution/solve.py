import csv
from decimal import ROUND_HALF_UP, Decimal

subtotal = Decimal("0")
with open("invoice.csv", newline="", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        subtotal += Decimal(row["quantity"]) * Decimal(row["unit_price"])

tax = (subtotal * Decimal("0.0825")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
total = subtotal + tax
print("Total: ${:,.2f}".format(total))
