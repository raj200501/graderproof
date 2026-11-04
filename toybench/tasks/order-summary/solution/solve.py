import json
from collections import Counter

orders = []
with open("orders.jsonl", encoding="utf-8") as fh:
    for line in fh:
        if line.strip():
            orders.append(json.loads(line))

units = Counter()
revenue = 0.0
for order in orders:
    units[order["product"]] += order["quantity"]
    revenue += order["quantity"] * order["unit_price"]

summary = {
    "orders": len(orders),
    "units": sum(units.values()),
    "revenue": round(revenue, 2),
    "top_product": units.most_common(1)[0][0],
}
with open("summary.json", "w", encoding="utf-8") as fh:
    fh.write(json.dumps(summary) + "\n")
