"""
Flow actor abstraction.
"""

import abc
import collections
import inspect
import io
import pickle
import types
import typing

import joblib

DataT = typing.TypeVar('DataT')


class Actor(typing.Generic[DataT], metaclass=abc.ABCMeta):
    """Abstract interface of an actor.
    """
    @classmethod
    def is_stateful(cls) -> bool:
        """Check whether this actor is stateful (determined based on existence user-overridden train method).

        Returns: True if stateful.
        """
        return cls.train.__code__ is not Actor.train.__code__

    def train(self, features: DataT, label: DataT) -> None:
        """Train the actor using the provided features and label.

        Args:
            features: Table of feature vectors.
            label: Table of labels.
        """
        raise NotImplementedError('Stateless actor')

    @abc.abstractmethod
    def apply(self, *features: DataT) -> typing.Union[DataT, typing.Sequence[DataT]]:
        """Pass features through the apply function (typically transform or predict).

        Args:
            features: Table(s) of feature vectors.

        Returns: Transformed features (ie predictions).
        """

    def get_params(self) -> typing.Dict[str, typing.Any]:
        """Get hyper-parameters of this actor.

        Default implementation is poor-mans init inspection and is expected to be overridden if not suitable.
        """
        return {p.name: p.default for p in inspect.signature(self.__class__).parameters.values() if
                p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD and p.default is not inspect.Parameter.empty}

    @abc.abstractmethod
    def set_params(self, params: typing.Optional[typing.Mapping[str, typing.Any]] = None,
                   **kwparams: typing.Any) -> None:
        """Set hyper-parameters of this actor.

        Args:
            params: Dictionary of hyper parameters.
        """

    def get_state(self) -> bytes:
        """Return the internal state of the actor.

        Returns: state as bytes.
        """
        if not self.is_stateful():
            return bytes()
        with io.BytesIO() as bio:
            joblib.dump(self.__dict__, bio, protocol=pickle.HIGHEST_PROTOCOL)
            return bio.getvalue()

    def set_state(self, state: bytes) -> None:
        """Set new internal state of the actor. Note this doesn't change the setting of the actor hyper-parameters.

        Args:
            state: bytes to be used as internal state.
        """
        if not state:
            return
        assert self.is_stateful(), 'State provided but actor stateless'
        params = self.get_params()  # keep the original hyper-params
        with io.BytesIO(state) as bio:
            self.__dict__.update(joblib.load(bio))
        self.set_params(**params)  # restore the original hyper-params

    def __str__(self):
        return self.__class__.__name__


class Spec(collections.namedtuple('Spec', 'actor, params')):
    """Wrapper of actor class and init params.
    """
    def __new__(cls, actor: typing.Type[Actor], **params: typing.Any):
        return super().__new__(cls, actor, types.MappingProxyType(params))

    def __str__(self):
        return self.actor.__name__ if inspect.isclass(self.actor) else str(self.actor)

    def __hash__(self):
        return hash(self.actor) ^ hash(tuple(sorted(self.params.items())))

    def __getnewargs_ex__(self):
        return (self.actor, ), dict(self.params)

    def __call__(self, **kwargs) -> Actor:
        return self.actor(**{**self.params, **kwargs})


class Wrapping:
    """Base class for actor wrapping.
    """
    def __init__(self, actor: typing.Type, mapping: typing.Mapping[str, str]):
        self._actor: typing.Any = actor
        self._mapping: typing.Mapping[str, str] = mapping

    def is_stateful(self) -> bool:
        """Emulation of native actor is_stateful class method.

        Returns: True if the wrapped actor is stateful (has a train method).
        """
        return hasattr(self._actor, self._mapping[Actor.train.__name__])


class Wrapped(Wrapping):
    """Decorator wrapper.
    """
    class Actor(Wrapping, Actor):  # pylint: disable=abstract-method
        """Wrapper around user class implementing the Actor interface.
        """
        def __new__(cls, actor: typing.Any, mapping: typing.Mapping[str, str]):  # pylint: disable=unused-argument
            cls.__abstractmethods__ = frozenset()
            return super().__new__(cls)

        def __init__(self, actor: typing.Any, mapping: typing.Mapping[str, str]):
            super().__init__(actor, mapping)

        def __getnewargs__(self):
            return self._actor, self._mapping

        def __getattribute__(self, item):
            if item.startswith('_') or item not in self._mapping and not hasattr(self._actor, item):
                return super().__getattribute__(item)
            return getattr(self._actor, self._mapping.get(item, item))

    def __init__(self, actor: typing.Type, mapping: typing.Mapping[str, str]):
        assert not issubclass(actor, Actor), 'Wrapping a true actor'
        super().__init__(actor, mapping)

    def __str__(self):
        return str(self._actor.__name__)

    def __call__(self, *args, **kwargs) -> Actor:
        return self.Actor(self._actor(*args, **kwargs), self._mapping)  # pylint: disable=abstract-class-instantiated

    def __hash__(self):
        return hash(self._actor) ^ hash(tuple(sorted(self._mapping.items())))

    def __eq__(self, other: typing.Any):
        # pylint: disable=protected-access
        return isinstance(other, self.__class__) and self._actor == other._actor and self._mapping == other._mapping

    @staticmethod
    def actor(cls: typing.Optional[typing.Type] = None, **mapping: str):  # pylint: disable=bad-staticmethod-argument
        """Decorator for turning an user class to a valid actor. This can be used either as parameterless decorator or
        optionally with mapping of Actor methods to decorated user class implementation.

        Args:
            cls: Decorated class.
            apply: Name of user class method implementing the actor apply.
            train: Name of user class method implementing the actor train.
            get_params: Name of user class method implementing the actor get_params.
            set_params: Name of user class method implementing the actor set_params.

        Returns: Actor class.
        """
        assert all(isinstance(a, str) for a in mapping.values()), 'Invalid mapping'

        for method in (Actor.apply, Actor.train, Actor.get_params, Actor.set_params):
            mapping.setdefault(method.__name__, method.__name__)

        def decorator(cls):
            """Decorating function.
            """
            assert cls and inspect.isclass(cls), f'Invalid actor class {cls}'
            if isinstance(cls, Actor):
                return cls
            for target in {t for s, t in mapping.items() if s != Actor.train.__name__}:
                assert callable(getattr(cls, target, None)), f'Wrapped actor missing required {target} implementation'
            return Wrapped(cls, mapping)

        if cls:
            decorator = decorator(cls)
        return decorator
