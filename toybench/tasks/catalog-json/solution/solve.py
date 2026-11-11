import csv
import json

with open("products.csv", newline="", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))

products = []
for row in rows:
    products.append(
        {
            "sku": row["sku"],
            "name": row["name"],
            "price": float(row["price"]),
            "in_stock": row["in_stock"].strip().lower() == "yes",
        }
    )

with open("products.json", "w", encoding="utf-8") as fh:
    json.dump(products, fh, indent=2)
    fh.write("\n")
