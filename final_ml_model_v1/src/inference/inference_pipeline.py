import joblib
import pandas as pd

from src.utils.logger import inference_logger
from src.explain.shap_explainer import SHAPExplainer
from src.alerts.alert_generator import AlertGenerator


class InferencePipeline:
    """
    Production inference pipeline for MemSOC.

    Flow:
        JSON
        -> DataFrame
        -> Validation
        -> Preprocessing
        -> Binary classification
        -> Multiclass classification (if attack)
        -> SHAP explanation
        -> Alert generation
    """

    def __init__(
        self,
        binary_model_path="models/binary_lightgbm.pkl",
        multiclass_model_path="models/multiclass_lightgbm.pkl",
    ):

        inference_logger.info("========== INITIALIZING INFERENCE PIPELINE ==========")

        # --------------------------------------------------
        # Load models
        # --------------------------------------------------

        inference_logger.info("Loading Binary LightGBM model...")

        self.binary_model = joblib.load(
            binary_model_path
        )

        inference_logger.info("Binary model loaded successfully.")

        inference_logger.info("Loading Multiclass LightGBM model...")

        self.multiclass_model = joblib.load(
            multiclass_model_path
        )

        inference_logger.info(
            "Multiclass model loaded successfully."
        )

        # --------------------------------------------------
        # Feature schema
        # --------------------------------------------------

        self.feature_names = list(
            self.binary_model.feature_name_
        )

        inference_logger.info(
            f"Expected features: {len(self.feature_names)}"
        )

        if len(self.feature_names) != 48:

            raise ValueError(
                "Expected exactly 48 model features."
            )

        # Verify both models use the same features

        multiclass_features = list(
            self.multiclass_model.feature_name_
        )

        if self.feature_names != multiclass_features:

            raise ValueError(
                "Binary and Multiclass model feature schemas do not match."
            )

        # --------------------------------------------------
        # SHAP
        # --------------------------------------------------

        self.shap_explainer = SHAPExplainer(
            multiclass_model_path
        )

        # --------------------------------------------------
        # Alert generator
        # --------------------------------------------------

        self.alert_generator = AlertGenerator()

        inference_logger.info(
            "Inference pipeline initialized successfully."
        )

    # ======================================================
    # VALIDATION
    # ======================================================

    def validate_input(self, data):

        inference_logger.info(
            "Validating incoming network flow..."
        )

        if not isinstance(data, dict):

            raise ValueError(
                "Input must be a JSON object."
            )

        missing_features = [
            feature
            for feature in self.feature_names
            if feature not in data
        ]

        if missing_features:

            raise ValueError(
                "Missing required features: "
                + ", ".join(missing_features)
            )

        inference_logger.info(
            "Input validation successful."
        )

    # ======================================================
    # DATAFRAME CREATION
    # ======================================================

    def prepare_dataframe(self, data):

        inference_logger.info(
            "Creating inference DataFrame..."
        )

        # Only use model features.
        # This prevents unexpected fields from entering
        # the model.

        sample = pd.DataFrame(
            [[
                data[feature]
                for feature in self.feature_names
            ]],
            columns=self.feature_names
        )

        # Convert numeric values

        for feature in self.feature_names:

            sample[feature] = pd.to_numeric(
                sample[feature],
                errors="coerce"
            )

        # Check for invalid values

        if sample.isna().any().any():

            invalid_features = (
                sample.columns[
                    sample.isna().any()
                ].tolist()
            )

            raise ValueError(
                "Invalid or missing numeric values in: "
                + ", ".join(invalid_features)
            )

        inference_logger.info(
            "Inference DataFrame prepared."
        )

        return sample

    # ======================================================
    # BINARY PREDICTION
    # ======================================================

    def binary_prediction(self, sample):

        inference_logger.info(
            "Running Binary LightGBM prediction..."
        )

        prediction = self.binary_model.predict(
            sample
        )[0]

        probabilities = (
            self.binary_model.predict_proba(
                sample
            )[0]
        )

        confidence = float(
            probabilities[int(prediction)]
        )

        if int(prediction) == 1:

            label = "Attack"

        else:

            label = "Benign"

        inference_logger.info(
            f"Binary prediction: {label}"
        )

        inference_logger.info(
            f"Binary confidence: {confidence:.4f}"
        )

        return (
            int(prediction),
            label,
            confidence
        )

    # ======================================================
    # MULTICLASS PREDICTION
    # ======================================================

    def multiclass_prediction(self, sample):

        inference_logger.info(
            "Running Multiclass LightGBM prediction..."
        )

        prediction = self.multiclass_model.predict(
            sample
        )[0]

        probabilities = (
            self.multiclass_model.predict_proba(
                sample
            )[0]
        )

        classes = list(
            self.multiclass_model.classes_
        )

        class_index = classes.index(
            prediction
        )

        confidence = float(
            probabilities[class_index]
        )

        inference_logger.info(
            f"Multiclass prediction: {prediction}"
        )

        inference_logger.info(
            f"Multiclass confidence: {confidence:.4f}"
        )

        return (
            prediction,
            confidence
        )

    # ======================================================
    # COMPLETE INFERENCE
    # ======================================================

    def predict(self, data):

        inference_logger.info(
            "========== STARTING INFERENCE =========="
        )

        # --------------------------------------------------
        # 1. Validate
        # --------------------------------------------------

        self.validate_input(
            data
        )

        # --------------------------------------------------
        # 2. Prepare DataFrame
        # --------------------------------------------------

        sample = self.prepare_dataframe(
            data
        )

        # --------------------------------------------------
        # 3. Binary classification
        # --------------------------------------------------

        (
            binary_prediction,
            binary_label,
            binary_confidence
        ) = self.binary_prediction(
            sample
        )

        # --------------------------------------------------
        # BENIGN PATH
        # --------------------------------------------------

        if binary_prediction == 0:

            inference_logger.info(
                "Flow classified as BENIGN."
            )

            return {
                "status": "benign",

                "binary": {
                    "prediction": binary_label,
                    "confidence": round(
                        binary_confidence,
                        4
                    )
                },

                "multiclass": None,

                "shap": None,

                "alert": None
            }

        # --------------------------------------------------
        # ATTACK PATH
        # --------------------------------------------------

        (
            attack,
            attack_confidence
        ) = self.multiclass_prediction(
            sample
        )

        # --------------------------------------------------
        # SHAP
        # --------------------------------------------------

        inference_logger.info(
            "Generating SHAP explanation..."
        )

        shap_explanation = (
            self.shap_explainer.explain(
                sample,
                top_k=10
            )
        )

        # --------------------------------------------------
        # Top features
        # --------------------------------------------------

        top_features = [
            item["feature"]
            for item in shap_explanation
        ]

        # --------------------------------------------------
        # Alert
        # --------------------------------------------------

        alert = self.alert_generator.generate(
            attack=attack,
            confidence=attack_confidence,
            flow=data,
            top_features=top_features,
            shap_explanation=shap_explanation
        )

        inference_logger.info(
            "Inference completed successfully."
        )

        # --------------------------------------------------
        # Final response
        # --------------------------------------------------

        return {
            "status": "attack",

            "binary": {
                "prediction": binary_label,
                "confidence": round(
                    binary_confidence,
                    4
                )
            },

            "multiclass": {
                "prediction": attack,
                "confidence": round(
                    attack_confidence,
                    4
                )
            },

            "shap": shap_explanation,

            "alert": alert
        }