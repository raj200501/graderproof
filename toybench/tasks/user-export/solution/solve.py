import csv
import json

with open("users.csv", newline="", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))

with open("users.jsonl", "w", encoding="utf-8") as fh:
    for row in rows:
        month, day, year = row["signup_date"].split("/")
        record = {
            "id": int(row["id"]),
            "name": "%s %s" % (row["first_name"], row["last_name"]),
            "email": row["email"].lower(),
            "signup": "%s-%s-%s" % (year, month, day),
        }
        fh.write(json.dumps(record) + "\n")
