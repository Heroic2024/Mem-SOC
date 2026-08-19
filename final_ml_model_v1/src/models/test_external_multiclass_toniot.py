import joblib
import pandas as pd

from src.utils.logger import logger


DATASET_PATH = "data/external/NF-ToN-IoT-v3.csv"
MODEL_PATH = "models/multiclass_lightgbm.pkl"

SAMPLES_PER_ATTACK = 1000
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


EXPECTED_ATTACK_CATEGORIES = {
    "ddos",
    "xss",
    "password",
    "scanning",
    "injection",
    "dos",
    "Backdoor",
    "mitm",
    "ransomware",
}


def main():

    logger.info(
        "========== NF-ToN-IoT MULTICLASS BEHAVIOR TEST =========="
    )

    # ==================================================
    # LOAD MODEL
    # ==================================================

    logger.info(
        "Loading finalized Multiclass LightGBM model..."
    )

    model = joblib.load(
        MODEL_PATH
    )

    expected_features = model.feature_name_

    logger.info(
        f"Expected model features: "
        f"{len(expected_features)}"
    )

    # ==================================================
    # COLLECT SAMPLES
    # ==================================================

    collected = {
        attack_name: []
        for attack_name in EXPECTED_ATTACK_CATEGORIES
    }

    logger.info(
        "Collecting samples from all NF-ToN-IoT "
        "attack categories..."
    )

    for chunk_number, df in enumerate(
        pd.read_csv(
            DATASET_PATH,
            chunksize=CHUNK_SIZE
        ),
        start=1
    ):

        logger.info(
            f"Reading chunk {chunk_number}..."
        )

        df["Label"] = pd.to_numeric(
            df["Label"],
            errors="coerce"
        )

        attacks = df[
            df["Label"] == 1
        ]

        if attacks.empty:
            continue

        # ----------------------------------------------
        # Collect each category
        # ----------------------------------------------

        for attack_name in EXPECTED_ATTACK_CATEGORIES:

            current_count = sum(
                len(part)
                for part in collected[attack_name]
            )

            if current_count >= SAMPLES_PER_ATTACK:
                continue

            category_samples = attacks[
                attacks["Attack"] == attack_name
            ]

            if category_samples.empty:
                continue

            remaining = (
                SAMPLES_PER_ATTACK
                - current_count
            )

            category_samples = category_samples.head(
                remaining
            )

            collected[attack_name].append(
                category_samples.copy()
            )

        # ----------------------------------------------
        # Stop once every category has enough samples
        # ----------------------------------------------

        complete = True

        for attack_name in EXPECTED_ATTACK_CATEGORIES:

            current_count = sum(
                len(part)
                for part in collected[attack_name]
            )

            if current_count < SAMPLES_PER_ATTACK:

                complete = False
                break

        if complete:

            logger.info(
                "All attack categories have enough samples."
            )

            break

    # ==================================================
    # SAMPLE COLLECTION SUMMARY
    # ==================================================

    print(
        "\n========== SAMPLE COLLECTION SUMMARY ==========\n"
    )

    test_parts = []

    for attack_name in sorted(
        EXPECTED_ATTACK_CATEGORIES
    ):

        parts = collected[attack_name]

        count = sum(
            len(part)
            for part in parts
        )

        print(
            f"{attack_name:<20} {count}"
        )

        if count > 0:

            attack_df = pd.concat(
                parts,
                ignore_index=True
            )

            test_parts.append(
                attack_df
            )

    if not test_parts:

        raise RuntimeError(
            "No attack samples were collected."
        )

    # ==================================================
    # COMBINE TEST DATA
    # ==================================================

    test_df = pd.concat(
        test_parts,
        ignore_index=True
    )

    logger.info(
        f"Total external attack samples collected: "
        f"{len(test_df):,}"
    )

    # ==================================================
    # PREPARE FEATURES
    # ==================================================

    X_test = test_df.drop(
        columns=DROP_COLUMNS
    )

    if "SRC_TO_DST_SECOND_BYTES" in X_test.columns:

        X_test[
            "SRC_TO_DST_SECOND_BYTES"
        ] = X_test[
            "SRC_TO_DST_SECOND_BYTES"
        ].fillna(0)

    logger.info(
        f"External feature shape: "
        f"{X_test.shape}"
    )

    # ==================================================
    # FEATURE COMPATIBILITY
    # ==================================================

    if list(X_test.columns) != list(
        expected_features
    ):

        print("\nExpected features:")
        print(expected_features)

        print("\nReceived features:")
        print(list(X_test.columns))

        raise ValueError(
            "External dataset features "
            "do not match trained model."
        )

    logger.info(
        "Feature compatibility verified."
    )

    # ==================================================
    # PREDICTIONS
    # ==================================================

    logger.info(
        "Running multiclass predictions..."
    )

    predictions = model.predict(
        X_test
    )

    probabilities = model.predict_proba(
        X_test
    )

    test_df["Prediction"] = predictions

    test_df["Confidence"] = (
        probabilities.max(axis=1)
    )

    # ==================================================
    # MODEL INFORMATION
    # ==================================================

    print(
        "\n=========================================================="
    )

    print(
        "       NF-ToN-IoT MULTICLASS BEHAVIOR TEST"
    )

    print(
        "=========================================================="
    )

    print(
        f"Total samples tested: "
        f"{len(test_df):,}"
    )

    print(
        "\nModel classes:"
    )

    print(
        list(model.classes_)
    )

    # ==================================================
    # PER-CATEGORY RESULTS
    # ==================================================

    for attack_name in sorted(
        test_df["Attack"].unique()
    ):

        category_df = test_df[
            test_df["Attack"] == attack_name
        ]

        print(
            "\n----------------------------------------------------------"
        )

        print(
            f"NF-ToN-IoT Attack: "
            f"{attack_name}"
        )

        print(
            f"Samples: "
            f"{len(category_df)}"
        )

        print(
            "\nPredicted classes:"
        )

        distribution = (
            category_df["Prediction"]
            .value_counts()
        )

        print(
            distribution
        )

        print(
            "\nAverage confidence:"
        )

        print(
            f"{category_df['Confidence'].mean():.4f}"
        )

    print(
        "\n=========================================================="
    )

    print(
        "MULTICLASS BEHAVIOR TEST COMPLETED"
    )

    print(
        "=========================================================="
    )


if __name__ == "__main__":
    main()