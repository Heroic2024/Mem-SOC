import joblib
import lightgbm as lgb

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)

from memsoc.detection.utils.logger import logger


class MulticlassTrainer:

    def __init__(self, X_train, X_test, y_train, y_test):

        self.X_train = X_train
        self.X_test = X_test
        self.y_train = y_train
        self.y_test = y_test

        # Final moderate class weights
        # Higher weights give more importance to minority classes.
        class_weight = {
            "Analysis": 4.0,
            "Backdoor": 2.0,
            "DoS": 1.8,
            "Exploits": 0.5,
            "Fuzzers": 0.6,
            "Generic": 0.8,
            "Reconnaissance": 0.9,
            "Shellcode": 3.0,
            "Worms": 5.0,
        }

        # Final Multiclass LightGBM configuration
        self.model = lgb.LGBMClassifier(
            objective="multiclass",
            n_estimators=600,
            learning_rate=0.03,
            random_state=42,
            class_weight=class_weight,
            num_leaves=63,
            min_child_samples=50,
            n_jobs=-1,
        )

    def train(self):

        logger.info(
            "Training Multiclass LightGBM Model..."
        )

        self.model.fit(
            self.X_train,
            self.y_train
        )

        logger.info(
            "Training Completed."
        )

    def evaluate(self):

        logger.info(
            "Evaluating Multiclass Model..."
        )

        predictions = self.model.predict(
            self.X_test
        )

        # ----------------------------------------------------
        # Overall Accuracy
        # ----------------------------------------------------

        accuracy = accuracy_score(
            self.y_test,
            predictions
        )

        logger.info(
            f"Accuracy : {accuracy:.4f}"
        )

        # ----------------------------------------------------
        # Confusion Matrix
        # ----------------------------------------------------

        print(
            "\nConfusion Matrix\n"
        )

        print(
            confusion_matrix(
                self.y_test,
                predictions
            )
        )

        # ----------------------------------------------------
        # Classification Report
        # ----------------------------------------------------

        print(
            "\nClassification Report\n"
        )

        print(
            classification_report(
                self.y_test,
                predictions
            )
        )

        # ----------------------------------------------------
        # Class-wise Performance
        # ----------------------------------------------------

        precision, recall, f1, support = (
            precision_recall_fscore_support(
                self.y_test,
                predictions,
                zero_division=0
            )
        )

        class_names = self.model.classes_

        print(
            "\n========== CLASS-WISE PERFORMANCE ==========\n"
        )

        for i, class_name in enumerate(class_names):

            print(
                f"{str(class_name):<18} "
                f"Precision: {precision[i]:.4f} | "
                f"Recall: {recall[i]:.4f} | "
                f"F1: {f1[i]:.4f} | "
                f"Samples: {support[i]}"
            )

    def save_model(self):

        joblib.dump(
            self.model,
            "models/multiclass_lightgbm.pkl"
        )

        logger.info(
            "Multiclass model saved successfully."
        )

    def predict(self, sample):

        prediction = self.model.predict(
            sample
        )[0]

        confidence = self.model.predict_proba(
            sample
        ).max()

        return prediction, confidence

    def top_features(
        self,
        sample,
        top_k=5
    ):

        import pandas as pd

        importance = pd.Series(
            self.model.feature_importances_,
            index=sample.columns
        )

        return (
            importance
            .sort_values(
                ascending=False
            )
            .head(top_k)
            .index
            .tolist()
        )

    def run(self):

        logger.info(
            "========== MULTICLASS MODEL TRAINING =========="
        )

        self.train()

        self.evaluate()

        self.save_model()