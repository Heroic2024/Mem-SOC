import pandas as pd

from memsoc.detection.inference.inference_pipeline import InferencePipeline


DATASET_PATH = "data/raw/NF-UNSW-NB15-v3.csv"


def main():

    print("\n========== MEMSOC ATTACK INFERENCE TEST ==========\n")

    # Find the first attack record
    attack_row = None

    for chunk in pd.read_csv(
        DATASET_PATH,
        chunksize=10000
    ):

        attacks = chunk[
            chunk["Label"] == 1
        ]

        if not attacks.empty:

            attack_row = attacks.iloc[0]

            break

    if attack_row is None:

        raise RuntimeError(
            "No attack record found in NF-UNSW dataset."
        )

    # Convert to DataFrame
    sample_df = pd.DataFrame(
        [attack_row]
    )

    # Keep ground truth only for displaying what
    # the dataset says. These values are NOT
    # passed to the inference pipeline.

    ground_truth_label = attack_row["Label"]
    ground_truth_attack = attack_row["Attack"]

    print(
        f"Ground-truth Label : {ground_truth_label}"
    )

    print(
        f"Ground-truth Attack : {ground_truth_attack}"
    )

    # Remove fields that are not model inputs
    drop_columns = [
        "Attack",
        "Label",
        "IPV4_SRC_ADDR",
        "IPV4_DST_ADDR",
        "FLOW_START_MILLISECONDS",
        "FLOW_END_MILLISECONDS",
        "DNS_QUERY_ID"
    ]

    sample = sample_df.drop(
        columns=drop_columns
    ).iloc[0].to_dict()

    print(
        f"Input features      : {len(sample)}"
    )

    # Initialize inference pipeline
    pipeline = InferencePipeline()

    # Run inference
    result = pipeline.predict(
        sample
    )

    print(
        "\n========== INFERENCE RESULT ==========\n"
    )

    print(result)


if __name__ == "__main__":
    main()