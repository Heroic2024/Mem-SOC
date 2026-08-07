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
from src.explainability.local_explainer import LocalExplainer
from src.alerts.alert_generator import AlertGenerator
from src.explainability.local_explainer import LocalExplainer
from src.models.analyze_multiclass import MulticlassAnalyzer


loader = DatasetLoader(Path("data/raw/NF-UNSW-NB15-v3.csv"))

df = loader.load()

validator = DataValidator(df)

validator.validate()

eda = EDA(df)

eda.run()

preprocessor = DataPreprocessor(df)

df = preprocessor.run()

feature_engineer = FeatureEngineering(df)

X, y_binary, y_multi = feature_engineer.run()

splitter = DataSplitter(X, y_binary, y_multi)

X_train_bin, X_test_bin, y_train_bin, y_test_bin = splitter.split_binary()

X_train_multi, X_test_multi, y_train_multi, y_test_multi = splitter.split_multiclass()

analyzer = MulticlassAnalyzer(y_train_multi)

analyzer.analyze()

binary_model = BinaryTrainer(
    X_train_bin,
    X_test_bin,
    y_train_bin,
    y_test_bin
)

binary_model.run()

multiclass_model = MulticlassTrainer(
    X_train_multi,
    X_test_multi,
    y_train_multi,
    y_test_multi
)

multiclass_model.run()

logger.info("========== GENERATING SAMPLE ALERT ==========")

# Take the first attack sample from the test set
sample = X_test_multi.iloc[[0]]

prediction, confidence = multiclass_model.predict(sample)
print("Prediction:", prediction)
print("Confidence:", confidence)

top_features = multiclass_model.top_features(sample)

alert_generator = AlertGenerator()

alert = alert_generator.generate(
    attack=prediction,
    confidence=confidence,
    flow=sample.iloc[0],
    top_features=top_features
)