import pandas as pd

df = pd.read_csv("first_10_rows.csv")

# Show all columns without truncation
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)

print(df)
