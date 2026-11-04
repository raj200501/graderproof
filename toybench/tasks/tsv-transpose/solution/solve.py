with open("matrix.tsv", encoding="utf-8", newline="") as fh:
    rows = [line.split("\t") for line in fh.read().split("\n") if line != ""]

columns = list(zip(*rows))
with open("transposed.tsv", "w", encoding="utf-8", newline="") as fh:
    for column in columns:
        fh.write("\t".join(column) + "\n")
