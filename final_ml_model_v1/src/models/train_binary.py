import joblib
import lightgbm as lgb

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
)

from src.utils.logger import logger


class BinaryTrainer:

    def __init__(self, X_train, X_test, y_train, y_test):
        self.X_train = X_train
        self.X_test = X_test
        self.y_train = y_train
        self.y_test = y_test

        self.model = lgb.LGBMClassifier(
            objective="binary",
            n_estimators=200,
            learning_rate=0.05,
            random_state=42,
            class_weight="balanced",
            n_jobs=-1
        )

    def train(self):

        logger.info("Training Binary LightGBM Model...")

        self.model.fit(self.X_train, self.y_train)

        logger.info("Training Completed.")

    def evaluate(self):

        logger.info("Evaluating Model...")

        predictions = self.model.predict(self.X_test)

        logger.info(f"Accuracy  : {accuracy_score(self.y_test, predictions):.4f}")
        logger.info(f"Precision : {precision_score(self.y_test, predictions):.4f}")
        logger.info(f"Recall    : {recall_score(self.y_test, predictions):.4f}")
        logger.info(f"F1 Score  : {f1_score(self.y_test, predictions):.4f}")

        print("\nConfusion Matrix\n")
        print(confusion_matrix(self.y_test, predictions))

        print("\nClassification Report\n")
        print(classification_report(self.y_test, predictions))

    def save_model(self):

        joblib.dump(self.model, "models/binary_lightgbm.pkl")

        logger.info("Binary model saved successfully.")

    def run(self):

        logger.info("========== BINARY MODEL TRAINING ==========")

        self.train()

        self.evaluate()

        self.save_model()