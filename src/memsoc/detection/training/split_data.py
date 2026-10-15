from sklearn.model_selection import train_test_split

from memsoc.detection.utils.logger import logger


class DataSplitter:
    """
    Splits the dataset into training and testing sets.
    """

    def __init__(self, X, y_binary, y_multi):
        self.X = X
        self.y_binary = y_binary
        self.y_multi = y_multi

    def split_binary(self):

        logger.info("Splitting data for Binary Classification...")

        X_train, X_test, y_train, y_test = train_test_split(
            self.X,
            self.y_binary,
            test_size=0.2,
            random_state=42,
            stratify=self.y_binary
        )

        logger.info(f"X Train : {X_train.shape}")
        logger.info(f"X Test  : {X_test.shape}")
        logger.info(f"Y Train : {y_train.shape}")
        logger.info(f"Y Test  : {y_test.shape}")

        return X_train, X_test, y_train, y_test

    def split_multiclass(self):

        logger.info("Splitting data for Multi-class Classification...")

        # Remove benign traffic
        attack_df = self.X.copy()
        attack_df["Attack"] = self.y_multi
        attack_df["Label"] = self.y_binary

        attack_df = attack_df[attack_df["Label"] == 1]

        X_attack = attack_df.drop(columns=["Attack", "Label"])
        y_attack = attack_df["Attack"]

        X_train, X_test, y_train, y_test = train_test_split(
            X_attack,
            y_attack,
            test_size=0.2,
            random_state=42,
            stratify=y_attack
        )

        logger.info(f"Attack X Train : {X_train.shape}")
        logger.info(f"Attack X Test  : {X_test.shape}")
        logger.info(f"Attack Y Train : {y_train.shape}")
        logger.info(f"Attack Y Test  : {y_test.shape}")

        return X_train, X_test, y_train, y_test