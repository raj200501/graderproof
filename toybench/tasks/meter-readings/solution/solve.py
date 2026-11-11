import csv

readings = {}
with open("readings.csv", newline="", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        readings.setdefault(row["meter"], []).append((row["date"], int(row["reading_kwh"])))

with open("usage.csv", "w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh, lineterminator="\n")
    writer.writerow(["meter", "kwh"])
    for meter in sorted(readings):
        series = sorted(readings[meter])
        writer.writerow([meter, series[-1][1] - series[0][1]])
