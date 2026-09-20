import pandas as pd
import requests

from memsoc import paths


DATASET_PATH = paths.DATASET_CSV


# --------------------------------------------------
# Find one real attack record
# --------------------------------------------------

for chunk in pd.read_csv(
    DATASET_PATH,
    chunksize=10000
):

    attacks = chunk[
        chunk["Label"] == 1
    ]

    if not attacks.empty:

        row = attacks.iloc[0]

        break


# --------------------------------------------------
# Model input fields
# --------------------------------------------------

drop_columns = [
    "Attack",
    "Label",
    "IPV4_SRC_ADDR",
    "IPV4_DST_ADDR",
    "FLOW_START_MILLISECONDS",
    "FLOW_END_MILLISECONDS",
    "DNS_QUERY_ID"
]


payload = (
    row.drop(
        labels=drop_columns
    )
    .to_dict()
)


print("\n========== API TEST ==========\n")

print(
    "Ground Truth Label:",
    row["Label"]
)

print(
    "Ground Truth Attack:",
    row["Attack"]
)

print(
    "Features sent:",
    len(payload)
)


# --------------------------------------------------
# Send request
# --------------------------------------------------

response = requests.post(
    "http://127.0.0.1:8000/api/logs",
    json=payload
)


print(
    "\nHTTP Status:",
    response.status_code
)

print(
    "\nAPI Response:"
)

print(
    response.json()
)