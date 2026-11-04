import csv
import json
from datetime import datetime, timezone

with open("sales.csv", newline="", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))

report = {
    "date": rows[0]["date"],
    "stores": len(rows),
    "total": round(sum(float(row["amount"]) for row in rows), 2),
}
report["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with open("report.json", "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2)
    fh.write("\n")
