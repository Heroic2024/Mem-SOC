input_path = "NF-CICIDS2018-v3.csv"
output_path = "first_10_rows.csv"

with open(input_path, "r") as infile, open(output_path, "w") as outfile:
    for i, line in enumerate(infile):
        if i > 10:  # header (line 0) + first 10 data rows
            break
        outfile.write(line)

print(f"Saved first 10 rows to {output_path}")
