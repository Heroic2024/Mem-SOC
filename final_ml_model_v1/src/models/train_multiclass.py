import joblib
import lightgbm as lgb


from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
)

from src.utils.logger import logger


class MulticlassTrainer:

    def __init__(self, X_train, X_test, y_train, y_test):

        self.X_train = X_train
        self.X_test = X_test
        self.y_train = y_train
        self.y_test = y_test

        self.model = lgb.LGBMClassifier(
            objective="multiclass",
            n_estimators=200,
            learning_rate=0.05,
            random_state=42,
            class_weight="balanced",
            n_jobs=-1,
        )

    def train(self):

        logger.info("Training Multiclass LightGBM Model...")

        self.model.fit(self.X_train, self.y_train)

        logger.info("Training Completed.")

    def evaluate(self):

        logger.info("Evaluating Multiclass Model...")

        predictions = self.model.predict(self.X_test)

        logger.info(f"Accuracy : {accuracy_score(self.y_test, predictions):.4f}")

        print("\nConfusion Matrix\n")
        print(confusion_matrix(self.y_test, predictions))

        print("\nClassification Report\n")
        print(classification_report(self.y_test, predictions))

    def save_model(self):

        joblib.dump(self.model, "models/multiclass_lightgbm.pkl")

        logger.info("Multiclass model saved successfully.")

    def predict(self, sample):

        prediction = self.model.predict(sample)[0]

        confidence = self.model.predict_proba(sample).max()

        return prediction, confidence

    def top_features(self, sample, top_k=5):

        import pandas as pd

        importance = pd.Series(
            self.model.feature_importances_,
            index=sample.columns
         )

        return (
        importance
        .sort_values(ascending=False)
        .head(top_k)
        .index
        .tolist()
        )

    def run(self):

        logger.info("========== MULTICLASS MODEL TRAINING ==========")

        self.train()

        self.evaluate()

        self.save_model()
        