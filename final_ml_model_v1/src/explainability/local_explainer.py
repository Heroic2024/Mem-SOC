import shap

from src.utils.logger import logger


class LocalExplainer:

    def __init__(self, model):
        self.model = model

    def explain(self, sample):

        logger.info("Generating Local SHAP Explanation...")

        explainer = shap.TreeExplainer(self.model)

        shap_values = explainer(sample)

        # Get predicted class
        prediction = self.model.predict(sample)
        predicted_class = prediction[0]

        # Waterfall plot for the predicted class
        shap.plots.waterfall(
            shap_values[0, :, predicted_class],
            max_display=10
        )

        # Top 5 most important features
        top_indices = (
            abs(shap_values.values[0, :, predicted_class])
            .argsort()[::-1][:5]
        )

        feature_names = sample.columns

        top_features = [
            feature_names[i]
            for i in top_indices
        ]

        print("\nTop Features:")

        for feature in top_features:
            print(feature)

        logger.info("Local Explanation Generated.")

        return top_features