from memsoc.detection.utils.logger import logger


class MulticlassAnalyzer:

    def __init__(self, y_train):
        self.y_train = y_train

    def analyze(self):

        logger.info("========== MULTICLASS ANALYSIS ==========")

        print(self.y_train.value_counts())

        print("\nClass Percentages\n")

        print(
            (self.y_train.value_counts(normalize=True) * 100)
            .round(2)
        )