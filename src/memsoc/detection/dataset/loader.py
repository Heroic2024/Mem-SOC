from pathlib import Path
import pandas as pd

from memsoc.detection.utils.logger import logger


class DatasetLoader:

    def __init__(self, dataset_path: Path):
        self.dataset_path = dataset_path
        self.df = None

    def load(self) -> pd.DataFrame:
        """
        Load the dataset into a Pandas DataFrame.
        """

        logger.info("Loading dataset...")

        if not self.dataset_path.exists():
            raise FileNotFoundError(
                f"Dataset not found: {self.dataset_path}"
            )

        self.df = pd.read_csv(self.dataset_path)

        logger.info("Dataset loaded successfully.")

        return self.df