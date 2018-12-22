import abc
import typing

import pandas


class Actor(metaclass=abc.ABCMeta):
    """Abstract interface of an actor.
    """
    @abc.abstractmethod
    def train(self, features: pandas.DataFrame, label: pandas.Series) -> None:
        """Train the actor using the provided features and label.

        Args:
            features: Table of feature vectors.
            label: Table of labels.
        """

    @abc.abstractmethod
    def apply(self, features: pandas.DataFrame) -> pandas.DataFrame:
        """Pass features through the apply function (typically transform or predict).

        Args:
            features: Table of feature vectors.

        Returns: Transformed features (ie predictions).
        """

    @abc.abstractmethod
    def set_hyper(self, params: typing.Dict[str, typing.Any]) -> None:
        """Set hyper-parameters of this actor.

        Args:
            params: Dictionary of hyper parameters.
        """

    @abc.abstractmethod
    def get_state(self) -> bytes:
        """Return the internal state of the actor.

        Returns: state as bytes.
        """

    @abc.abstractmethod
    def set_state(self, state: bytes) -> None:
        """Set new internal state of the actor.

        Args:
            state: bytes to be used as internal state.
        """
