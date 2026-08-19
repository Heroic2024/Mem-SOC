import joblib
import pandas as pd

from sklearn.metrics import confusion_matrix

from src.utils.logger import logger


DATASET_PATH = "data/external/NF-ToN-IoT-v3.csv"
MODEL_PATH = "models/binary_lightgbm.pkl"

CHUNK_SIZE = 250_000

DROP_COLUMNS = [
    "Attack",
    "Label",
    "IPV4_SRC_ADDR",
    "IPV4_DST_ADDR",
    "FLOW_START_MILLISECONDS",
    "FLOW_END_MILLISECONDS",
    "DNS_QUERY_ID",
]


def main():

    logger.info(
        "========== FULL NF-ToN-IoT BINARY TEST =========="
    )

    # --------------------------------------------------
    # Load finalized model
    # --------------------------------------------------

    logger.info(
        "Loading finalized Binary LightGBM model..."
    )

    model = joblib.load(
        MODEL_PATH
    )

    expected_features = model.feature_name_

    logger.info(
        f"Expected model features: {len(expected_features)}"
    )

    # --------------------------------------------------
    # Counters
    # --------------------------------------------------

    total_samples = 0

    true_negative = 0
    false_positive = 0
    false_negative = 0
    true_positive = 0

    total_benign = 0
    total_attack = 0

    # --------------------------------------------------
    # Process complete dataset in chunks
    # --------------------------------------------------

    logger.info(
        f"Reading dataset in chunks of "
        f"{CHUNK_SIZE:,} rows..."
    )

    for chunk_number, df in enumerate(
        pd.read_csv(
            DATASET_PATH,
            chunksize=CHUNK_SIZE
        ),
        start=1
    ):

        logger.info(
            f"Processing chunk {chunk_number}..."
        )

        # --------------------------------------------------
        # Handle missing values
        # --------------------------------------------------

        if "SRC_TO_DST_SECOND_BYTES" in df.columns:

            df["SRC_TO_DST_SECOND_BYTES"] = (
                df["SRC_TO_DST_SECOND_BYTES"]
                .fillna(0)
            )

        # --------------------------------------------------
        # Extract labels
        # --------------------------------------------------

        y_true = df["Label"].astype(int)

        # --------------------------------------------------
        # Prepare features
        # --------------------------------------------------

        X = df.drop(
            columns=DROP_COLUMNS
        )

        # --------------------------------------------------
        # Verify feature compatibility
        # --------------------------------------------------

        if list(X.columns) != list(
            expected_features
        ):

            raise ValueError(
                "Feature mismatch detected."
            )

        # --------------------------------------------------
        # Predict
        # --------------------------------------------------

        predictions = model.predict(
            X
        ).astype(int)

        # --------------------------------------------------
        # Update confusion matrix
        # --------------------------------------------------

        tn, fp, fn, tp = confusion_matrix(
            y_true,
            predictions,
            labels=[0, 1]
        ).ravel()

        true_negative += tn
        false_positive += fp
        false_negative += fn
        true_positive += tp

        # --------------------------------------------------
        # Update totals
        # --------------------------------------------------

        total_samples += len(df)

        total_benign += (
            y_true == 0
        ).sum()

        total_attack += (
            y_true == 1
        ).sum()

        logger.info(
            f"Chunk {chunk_number} completed | "
            f"Samples processed: {total_samples:,}"
        )

    # ======================================================
    # FINAL METRICS
    # ======================================================

    accuracy = (
        true_negative + true_positive
    ) / total_samples

    precision = (
        true_positive /
        (true_positive + false_positive)
        if (true_positive + false_positive) > 0
        else 0
    )

    recall = (
        true_positive /
        (true_positive + false_negative)
        if (true_positive + false_negative) > 0
        else 0
    )

    f1 = (
        2 * precision * recall /
        (precision + recall)
        if (precision + recall) > 0
        else 0
    )

    false_positive_rate = (
        false_positive /
        (false_positive + true_negative)
        if (false_positive + true_negative) > 0
        else 0
    )

    # ======================================================
    # FINAL RESULTS
    # ======================================================

    print(
        "\n=================================================="
    )

    print(
        "       FULL NF-ToN-IoT BINARY TEST"
    )

    print(
        "=================================================="
    )

    print(
        f"Total Samples Tested : {total_samples:,}"
    )

    print(
        f"Total Benign         : {total_benign:,}"
    )

    print(
        f"Total Attack         : {total_attack:,}"
    )

    print(
        "\n---------------- METRICS ----------------\n"
    )

    print(
        f"Accuracy             : {accuracy:.4f}"
    )

    print(
        f"Precision            : {precision:.4f}"
    )

    print(
        f"Recall               : {recall:.4f}"
    )

    print(
        f"F1 Score             : {f1:.4f}"
    )

    print(
        f"False Positive Rate  : "
        f"{false_positive_rate:.4f}"
    )

    print(
        f"Attack Detection Rate : "
        f"{recall:.4f}"
    )

    print(
        "\n---------------- CONFUSION MATRIX ----------------\n"
    )

    print(
        "                 Predicted"
    )

    print(
        "                 Benign    Attack"
    )

    print(
        f"Actual Benign    "
        f"{true_negative:8d} "
        f"{false_positive:8d}"
    )

    print(
        f"Actual Attack    "
        f"{false_negative:8d} "
        f"{true_positive:8d}"
    )

    print(
        "\n=================================================="
    )

    print(
        "              TEST COMPLETED"
    )

    print(
        "=================================================="
    )


if __name__ == "__main__":
    main()