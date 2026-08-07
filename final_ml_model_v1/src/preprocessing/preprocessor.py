import pandas as pd

from src.utils.logger import logger


class DataPreprocessor:
    """
    Preprocesses the dataset before model training.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df

    def remove_duplicates(self):

        logger.info("Removing duplicate rows...")

        before = len(self.df)

        self.df = self.df.drop_duplicates()

        after = len(self.df)

        logger.info(f"Removed {before-after} duplicate rows.")

    def handle_missing_values(self):

        logger.info("Handling missing values...")

        self.df["SRC_TO_DST_SECOND_BYTES"] = self.df[
            "SRC_TO_DST_SECOND_BYTES"
        ].fillna(0)

        logger.info("Missing values handled.")

    def run(self):

        logger.info("========== PREPROCESSING ==========")

        self.remove_duplicates()

        self.handle_missing_values()

        logger.info("Preprocessing Completed.")

        return self.df