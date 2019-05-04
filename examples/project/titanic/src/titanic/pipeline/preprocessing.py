"""
Transformers useful for the Titanic example.

This module is informal from ForML perspective and has been created just for structuring the project code base.

Here we just create couple of forml operators that implement particular transformers.

We demonstrate three different ways of creating a forml operator:
  * Implementing native ForML actor (NanImputer)
  * Creating a wrapped actor from a Transformer-like class (TitleParser)
  * Wrapping a 3rd party Transformer-like class (ENCODER)
"""
import typing

import category_encoders
import numpy
import pandas
from sklearn import base as skbase

from forml.flow import task
from forml.stdlib import actor
from forml.stdlib.operator import simple


@simple.Mapper.operator
class NaNImputer(task.Actor):
    """Imputer for missing values implemented as native ForML actor.
    """
    def __init__(self):
        self._fill: typing.Optional[pandas.Series] = None

    def train(self, data: pandas.DataFrame, label: pandas.Series) -> None:
        """Train the actor by learning the median for each numeric column and finding the most common value for strings.
        """
        self._fill = pandas.Series([data[c].value_counts().index[0] if data[c].dtype == numpy.dtype('O')
                                    else data[c].median() for c in data], index=data.columns)

    def apply(self, data: pandas.DataFrame) -> pandas.DataFrame:
        """Apply the imputation to the given dataset.
        """
        return data.fillna(self._fill)


@simple.Mapper.operator
@actor.Wrapped.actor(apply='transform')
class TitleParser(skbase.TransformerMixin):
    """Transformer extracting a person's title from the name string implemented as scikit-learn compatible transformer.
    """
    def __init__(self, source: str = 'name', target: str = 'title'):
        self.source = source
        self.target = target

    @staticmethod
    def get_title(name: str) -> str:
        """Auxiliary method for extracting the title.
        """
        if '.' in name:
            return name.split(',')[1].split('.')[0].strip()
        return 'Unknown'

    def transform(self, data: pandas.DataFrame) -> pandas.DataFrame:
        """Method required by the Sklearn API - transform.
        """
        data[self.target] = data[self.source].map(self.get_title)
        return data

    def get_params(self) -> typing.Mapping[str, str]:
        """Method required by the Sklearn API - get_params.
        """
        return dict(self.__dict__)

    def set_params(self, source: str = 'name', target: str = 'title'):
        """Method required by the Sklearn API - set_params.
        """
        self.source = source
        self.target = target


# 3rd party transformer wrapped as an actor into a mapper operator:
ENCODER = simple.Mapper.operator(actor.Wrapped.actor(category_encoders.HashingEncoder, train='fit', apply='transform'))
