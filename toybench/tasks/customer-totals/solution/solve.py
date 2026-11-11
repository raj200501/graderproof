import csv
from collections import defaultdict
from decimal import Decimal

totals = defaultdict(Decimal)
with open("payments.csv", newline="", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        totals[row["customer"]] += Decimal(row["amount"])

with open("totals.csv", "w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh, lineterminator="\n")
    writer.writerow(["customer", "total"])
    for customer in sorted(totals):
        writer.writerow([customer, "%.2f" % totals[customer]])
