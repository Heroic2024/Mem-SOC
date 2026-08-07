import pandas as pd

from src.utils.logger import logger


class DataValidator:
    """
    Performs validation checks on the loaded dataset.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df

    def check_missing_values(self):
        logger.info("Checking for missing values...")

        missing = self.df.isnull().sum()
        total_missing = missing.sum()

        logger.info(f"Total Missing Values: {total_missing}")

        if total_missing > 0:
            logger.info("Columns with missing values:")
            print(missing[missing > 0])

    def check_duplicates(self):
        logger.info("Checking for duplicate rows...")

        duplicates = self.df.duplicated().sum()

        logger.info(f"Duplicate Rows Found: {duplicates}")

    def dataset_shape(self):
        logger.info("Dataset Shape")
        logger.info(f"Rows    : {self.df.shape[0]}")
        logger.info(f"Columns : {self.df.shape[1]}")

    def memory_usage(self):
        memory = self.df.memory_usage(deep=True).sum() / (1024 ** 2)

        logger.info(f"Memory Usage : {memory:.2f} MB")

    def data_types(self):
        logger.info("Column Data Types")
        print(self.df.dtypes)

    def attack_distribution(self):
        logger.info("Attack Distribution")
        print(self.df["Attack"].value_counts())

    def label_distribution(self):
        logger.info("Label Distribution")
        print(self.df["Label"].value_counts())

    def constant_columns(self):
        logger.info("Checking constant columns...")

        constant_cols = [
            col for col in self.df.columns
            if self.df[col].nunique() == 1
        ]

        logger.info(f"Constant Columns Found: {len(constant_cols)}")

        if constant_cols:
            print(constant_cols)

    def validate(self):

        logger.info("========== DATASET VALIDATION ==========")

        self.dataset_shape()

        self.memory_usage()

        self.check_missing_values()

        self.check_duplicates()

        self.constant_columns()

        self.attack_distribution()

        self.label_distribution()

        logger.info("Validation completed successfully.")