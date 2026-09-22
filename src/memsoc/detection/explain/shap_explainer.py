import joblib
import shap
import numpy as np

from memsoc.detection.utils.logger import inference_logger


class SHAPExplainer:

    def __init__(self, model_path="models/multiclass_lightgbm.pkl"):

        inference_logger.info(
            "Loading multiclass model for SHAP explanation..."
        )

        self.model = joblib.load(model_path)

        inference_logger.info(
            "Multiclass model loaded successfully."
        )

        self.explainer = shap.TreeExplainer(
            self.model
        )

    def explain(self, sample, top_k=10):

        inference_logger.info(
            "Calculating SHAP feature contributions..."
        )

        # --------------------------------------------------
        # Get model prediction
        # --------------------------------------------------

        prediction = self.model.predict(sample)[0]

        # --------------------------------------------------
        # Convert predicted class label to class index
        # --------------------------------------------------

        classes = list(self.model.classes_)

        class_index = classes.index(prediction)

        inference_logger.info(
            f"Predicted class : {prediction}"
        )

        inference_logger.info(
            f"Predicted class index : {class_index}"
        )

        # --------------------------------------------------
        # Calculate SHAP values
        # --------------------------------------------------

        shap_values = self.explainer.shap_values(
            sample
        )

        # --------------------------------------------------
        # Handle different SHAP output formats
        # --------------------------------------------------

        if isinstance(shap_values, list):

            # Older SHAP versions:
            # one array for each class

            class_shap_values = shap_values[class_index][0]

        else:

            shap_values = np.asarray(
                shap_values
            )

            if shap_values.ndim == 3:

                # Newer SHAP format:
                #
                # (samples, features, classes)

                class_shap_values = (
                    shap_values[
                        0,
                        :,
                        class_index
                    ]
                )

            elif shap_values.ndim == 2:

                class_shap_values = (
                    shap_values[0]
                )

            else:

                class_shap_values = shap_values

        # --------------------------------------------------
        # Get feature names
        # --------------------------------------------------

        feature_names = sample.columns.tolist()

        # --------------------------------------------------
        # Build SHAP explanation
        # --------------------------------------------------

        feature_contributions = []

        for feature, value in zip(
            feature_names,
            class_shap_values
        ):

            feature_contributions.append(
                {
                    "feature": feature,
                    "shap_value": float(value),
                    "impact": (
                        "positive"
                        if value > 0
                        else "negative"
                    )
                }
            )

        # --------------------------------------------------
        # Sort by absolute SHAP importance
        # --------------------------------------------------

        feature_contributions.sort(
            key=lambda x: abs(
                x["shap_value"]
            ),
            reverse=True
        )

        # --------------------------------------------------
        # Return top features
        # --------------------------------------------------

        top_features = (
            feature_contributions[:top_k]
        )

        inference_logger.info(
            f"SHAP explanation generated "
            f"for class: {prediction}"
        )

        return top_features