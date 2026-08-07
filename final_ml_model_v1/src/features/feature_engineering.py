import pandas as pd

from src.utils.logger import logger


class FeatureEngineering:
    """
    Creates the feature matrix and target labels.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df

    def prepare_features(self):

        logger.info("Preparing training features...")

        columns_to_drop = [
            "Attack",
            "Label",
            "IPV4_SRC_ADDR",
            "IPV4_DST_ADDR",
            "FLOW_START_MILLISECONDS",
            "FLOW_END_MILLISECONDS",
            "DNS_QUERY_ID"
        ]

        X = self.df.drop(columns=columns_to_drop)

        y_binary = self.df["Label"]

        y_multi = self.df["Attack"]

        logger.info(f"Training Features Shape : {X.shape}")
        logger.info(f"Binary Labels Shape     : {y_binary.shape}")
        logger.info(f"Attack Labels Shape     : {y_multi.shape}")
        logger.info("Training Features")

        return X, y_binary, y_multi

    def run(self):

        logger.info("========== FEATURE ENGINEERING ==========")

        return self.prepare_features()