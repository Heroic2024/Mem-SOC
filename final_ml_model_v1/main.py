from pathlib import Path

from src.utils.logger import logger
from src.dataset.loader import DatasetLoader
from src.dataset.validator import DataValidator
from src.eda.eda import EDA
from src.preprocessing.preprocessor import DataPreprocessor
from src.features.feature_engineering import FeatureEngineering
from src.models.split_data import DataSplitter
from src.models.train_binary import BinaryTrainer
from src.models.train_multiclass import MulticlassTrainer
from src.alerts.alert_generator import AlertGenerator
from src.models.analyze_multiclass import MulticlassAnalyzer
from src.explain.shap_explainer import SHAPExplainer


# ============================================================
# DATASET LOADING
# ============================================================

loader = DatasetLoader(
    Path("data/raw/NF-UNSW-NB15-v3.csv")
)

df = loader.load()


# ============================================================
# DATASET VALIDATION
# ============================================================

validator = DataValidator(df)

validator.validate()


# ============================================================
# EDA
# ============================================================

eda = EDA(df)

eda.run()


# ============================================================
# PREPROCESSING
# ============================================================

preprocessor = DataPreprocessor(df)

df = preprocessor.run()


# ============================================================
# FEATURE ENGINEERING
# ============================================================

feature_engineer = FeatureEngineering(df)

X, y_binary, y_multi = feature_engineer.run()


# ============================================================
# DATA SPLITTING
# ============================================================

splitter = DataSplitter(
    X,
    y_binary,
    y_multi
)

X_train_bin, X_test_bin, y_train_bin, y_test_bin = (
    splitter.split_binary()
)

X_train_multi, X_test_multi, y_train_multi, y_test_multi = (
    splitter.split_multiclass()
)


# ============================================================
# MULTICLASS ANALYSIS
# ============================================================

analyzer = MulticlassAnalyzer(
    y_train_multi
)

analyzer.analyze()


# ============================================================
# BINARY MODEL
# ============================================================

binary_model = BinaryTrainer(
    X_train_bin,
    X_test_bin,
    y_train_bin,
    y_test_bin
)

binary_model.run()


# ============================================================
# MULTICLASS MODEL
# ============================================================

multiclass_model = MulticlassTrainer(
    X_train_multi,
    X_test_multi,
    y_train_multi,
    y_test_multi
)

multiclass_model.run()


# ============================================================
# SHAP EXPLAINER
# ============================================================

shap_explainer = SHAPExplainer()


# ============================================================
# ALERT GENERATOR
# ============================================================

alert_generator = AlertGenerator()


# ============================================================
# TEST 100 ATTACK SAMPLES
# ============================================================

logger.info(
    "========== TESTING 100 ATTACK SAMPLES =========="
)

num_samples = min(100, len(X_test_multi))

correct = 0
incorrect = 0

confidences = []

results = []


# ============================================================
# SAMPLE TESTING LOOP
# ============================================================

for index in range(num_samples):

    logger.info(
        f"Testing sample {index + 1}/{num_samples}"
    )

    # --------------------------------------------------------
    # Select sample
    # --------------------------------------------------------

    sample = X_test_multi.iloc[[index]]

    actual_label = str(
        y_test_multi.iloc[index]
    )


    # --------------------------------------------------------
    # Model prediction
    # --------------------------------------------------------

    prediction, confidence = (
        multiclass_model.predict(sample)
    )

    prediction = str(prediction)
    confidence = float(confidence)


    # --------------------------------------------------------
    # Check prediction
    # --------------------------------------------------------

    is_correct = (
        prediction == actual_label
    )

    if is_correct:
        correct += 1
    else:
        incorrect += 1


    confidences.append(
        confidence
    )


    # --------------------------------------------------------
    # Store result
    # --------------------------------------------------------

    results.append(
        {
            "index": index,
            "actual": actual_label,
            "predicted": prediction,
            "confidence": confidence,
            "correct": is_correct
        }
    )


    # --------------------------------------------------------
    # Print sample result
    # --------------------------------------------------------

    print(
        f"Sample {index:3d} | "
        f"Actual: {actual_label:<15} | "
        f"Predicted: {prediction:<15} | "
        f"Confidence: {confidence:.4f} | "
        f"{'YES' if is_correct else 'NO'}"
    )


# ============================================================
# CALCULATE 100-SAMPLE PERFORMANCE
# ============================================================

sample_accuracy = (
    correct / num_samples
)

average_confidence = (
    sum(confidences) / len(confidences)
)


# ============================================================
# 100-SAMPLE TEST SUMMARY
# ============================================================

print("\n")
print("=" * 60)
print("              100-SAMPLE TEST SUMMARY")
print("=" * 60)

print(
    f"Total Samples        : {num_samples}"
)

print(
    f"Correct Predictions  : {correct}"
)

print(
    f"Incorrect Predictions: {incorrect}"
)

print(
    f"Sample Accuracy      : {sample_accuracy:.4f}"
)

print(
    f"Sample Accuracy (%)  : {sample_accuracy * 100:.2f}%"
)

print(
    f"Average Confidence   : {average_confidence:.4f}"
)

print("=" * 60)


# ============================================================
# INCORRECT PREDICTIONS
# ============================================================

print(
    "\n========== INCORRECT PREDICTIONS ==========\n"
)

incorrect_results = [
    result
    for result in results
    if not result["correct"]
]


if len(incorrect_results) == 0:

    print(
        "No incorrect predictions."
    )

else:

    for result in incorrect_results:

        print(
            f"Sample {result['index']} | "
            f"Actual: {result['actual']} | "
            f"Predicted: {result['predicted']} | "
            f"Confidence: {result['confidence']:.4f}"
        )


# ============================================================
# SHAP EXPLANATION
# ============================================================

logger.info(
    "========== SHAP EXPLANATION =========="
)


# Find first correctly classified sample
correct_sample_index = None

for result in results:

    if result["correct"]:

        correct_sample_index = (
            result["index"]
        )

        break


if correct_sample_index is not None:

    sample = X_test_multi.iloc[
        [correct_sample_index]
    ]

    prediction, confidence = (
        multiclass_model.predict(sample)
    )

    shap_features = (
        shap_explainer.explain(
            sample,
            top_k=10
        )
    )


    print(
        "\n========== SHAP EXPLANATION ==========\n"
    )

    print(
        f"Sample Index : {correct_sample_index}"
    )

    print(
        f"Prediction   : {prediction}"
    )

    print(
        f"Confidence   : {float(confidence):.4f}"
    )

    print(
        "\nTop SHAP Features:\n"
    )


    for item in shap_features:

        print(
            f"{item['feature']:<30} "
            f"{item['shap_value']:+.6f} "
            f"({item['impact']})"
        )


    # ========================================================
    # GENERATE FINAL ALERT FOR SHAP SAMPLE
    # ========================================================

    top_features = (
        multiclass_model.top_features(
            sample
        )
    )


    alert = alert_generator.generate(
        attack=prediction,
        confidence=confidence,
        flow=sample.iloc[0],
        top_features=top_features,
        shap_explanation=shap_features
    )


    print(
        "\n========== FINAL ALERT ==========\n"
    )

    print(alert)

else:

    print(
        "\nNo correctly classified sample was found "
        "for SHAP explanation."
    )