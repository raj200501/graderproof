import csv
import json
from decimal import Decimal

totals = {}
with open("expenses.csv", newline="", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        totals[row["category"]] = totals.get(row["category"], Decimal("0")) + Decimal(row["amount"])

with open("by_category.csv", "w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh, lineterminator="\n")
    writer.writerow(["category", "total"])
    for category in sorted(totals):
        writer.writerow([category, "%.2f" % totals[category]])

summary = {"categories": len(totals), "grand_total": float(round(sum(totals.values()), 2))}
with open("summary.json", "w", encoding="utf-8") as fh:
    json.dump(summary, fh)
    fh.write("\n")
