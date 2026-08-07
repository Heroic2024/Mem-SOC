import matplotlib.pyplot as plt
import pandas as pd

from src.utils.logger import logger


class EDA:
    """
    Performs Exploratory Data Analysis on the dataset.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df

    def attack_distribution(self):

        logger.info("Generating Attack Distribution...")

        attack_counts = self.df["Attack"].value_counts()

        print(attack_counts)

        plt.figure(figsize=(10, 6))
        attack_counts.plot(kind="bar")

        plt.title("Attack Distribution")
        plt.xlabel("Attack Type")
        plt.ylabel("Count")

        plt.xticks(rotation=45)

        plt.tight_layout()

        plt.savefig("outputs/attack_distribution.png")

        plt.close()

    def run(self):

        logger.info("Starting EDA...")

        self.attack_distribution()

        logger.info("EDA Completed.")