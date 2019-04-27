"""
Graph view - useful lenses and manipulation of graph topology parts.
"""

import abc
import collections
import itertools
import operator
import typing

from forml.flow import graph

from forml.flow.graph import node as grnode, port


class Visitor(grnode.Visitor):
    """Path visitor interface.
    """
    def visit_path(self, path: 'Path') -> None:
        """Path visit.

        Args:
            path: Path visit.
        """


class Traversal(collections.namedtuple('Traversal', 'current, predecessors')):
    """Graph traversal helper.
    """
    class Cyclic(AssertionError):
        """Cyclic graph error.
        """
    def __new__(cls, current: grnode.Atomic, predecessors: typing.AbstractSet[grnode.Atomic] = frozenset()):
        return super().__new__(cls, current, frozenset(predecessors | {current}))

    def directs(self, *extras: grnode.Atomic, mask: typing.Optional[
            typing.Callable[[grnode.Atomic], bool]] = None) -> typing.Iterator['Traversal']:
        """Utility for retrieving set of node subscribers with optional mask and list of potential Futures (that are not
        subscribed directly).

        Args:
            *extras: Future nodes that might be subscribed to this publisher.
            mask: Optional condition for filtering the subscriptions.

        Returns: Iterable of new Traversals.
        """
        seen = set()
        for node in itertools.chain((s.node for p in self.current.output for s in p),
                                    (e for e in extras if e and e.subscribed(self.current))):
            if node in seen or mask and not mask(node):
                continue
            if node in self.predecessors:
                raise self.Cyclic(f'Cyclic flow near {node}')
            seen.add(node)
            yield self.__class__(node, self.predecessors)

    def mappers(self, *extras: grnode.Atomic) -> typing.Iterator['Traversal']:
        """Return subscribers with specific mask to pass only mapper (not trained) nodes.

        Args:
            *extras: Future nodes that might be subscribed to this publisher.

        Returns: Subscribers instance.
        """
        return self.directs(*extras, mask=lambda n: not isinstance(n, grnode.Worker) or not n.trained)

    def tail(self, expected: typing.Optional[grnode.Atomic] = None) -> 'Traversal':
        """Recursive traversing all mapper subscription paths down to the tail mapper checking there is just one.

        Args:
            expected: Optional indication of the expected tail. If expected is a Future, it's matching Worker is
                      returned instead.

        Returns: Tail traversal of the flow.
        """
        if expected and self.current == expected:
            return self
        endings = set()
        for node in self.mappers(expected):
            tail = node.tail(expected)
            if expected and tail.current == expected:
                return tail
            endings.add(tail)
        if not any(endings):
            return self
        if len(self.predecessors) == 1 and (expected or len(endings) > 1):
            raise graph.Error('Ambiguous tail')
        return endings.pop()

    def each(self, tail: grnode.Atomic, acceptor: typing.Callable[[grnode.Atomic], None]) -> None:
        """Traverse the path downstream calling acceptor for each unique node.

        Args:
            tail: Optional traversion breakpoint.
            acceptor: Acceptor to call for each unique node.
        """
        def unseen(node: grnode.Atomic) -> bool:
            """Test for node recurrence.

            Args:
                node: Node instance to be checked for recurrence.

            Returns: True if not recurrent.
            """
            return node not in seen

        def traverse(traversal: Traversal) -> None:
            """Recursive path scan.

            Args:
                traversal: Node to be processed.
            """
            mask = unseen
            if traversal.current == tail:
                mask = lambda n: unseen(n) and n.trained
            acceptor(traversal.current)
            seen.add(traversal.current)
            for node in traversal.directs(tail, mask=mask):
                traverse(node)

        seen = set()
        traverse(Traversal(self.current))

    def copy(self, tail: grnode.Atomic) -> typing.Mapping[grnode.Atomic, grnode.Atomic]:
        """Make a copy of the apply path topology. Any nodes not on path are ignored.

        Only the main branch is copied ignoring all sink branches.

        Args:
            tail: Last node to copy.

        Returns: Copy of the apply path.
        """

        def traverse(traversal: Traversal) -> None:
            """Recursive path copy.

            Args:
                traversal: Node to be copied.

            Returns: Copy of the publisher node with all of it's subscriptions resolved.
            """
            if traversal.current == tail:
                for orig in traversal.predecessors:
                    pub = copies.get(orig) or copies.setdefault(orig, orig.fork())
                    for index, subscription in ((i, s) for i, p in enumerate(orig.output)
                                                for s in p if s.node in traversal.predecessors):
                        sub = copies.get(subscription.node) or copies.setdefault(
                            subscription.node, subscription.node.fork())
                        sub[subscription.port].subscribe(pub[index])
            else:
                for node in traversal.mappers(tail):
                    traverse(node)

        copies = dict()
        traverse(self)
        return copies


class Path(tuple, metaclass=abc.ABCMeta):
    """Representing acyclic apply path(s) between two nodes - a sub-graph with single head and tail node each with
    at most one apply input/output port.

    This is a base and factory class for creating specific path instances.
    """

    _head: grnode.Atomic = property(operator.itemgetter(0))
    _tail: grnode.Atomic = property(operator.itemgetter(1))

    def __new__(cls, head: grnode.Atomic, tail: typing.Optional[grnode.Atomic] = None):
        if head.szin not in {0, 1}:
            raise graph.Error('Simple head required')
        tail = Traversal(head).tail(tail).current
        if tail.szout not in {0, 1}:
            raise graph.Error('Simple tail required')
        # pylint: disable=self-cls-assignment
        cls = Closure if any(s.node.trained for p in tail.output for s in p) else Channel
        return super().__new__(cls, (head, tail))

    def accept(self, visitor: Visitor) -> None:
        """Visitor acceptor.

        Args:
            visitor: Visitor instance.
        """
        Traversal(self._head).each(self._tail, visitor.visit_node)
        visitor.visit_path(self)

    # @abc.abstractmethod
    def extend(self, right: typing.Optional['Path'] = None, tail: typing.Optional[grnode.Atomic] = None) -> 'Path':
        """Create new path by appending right head to our tail or traversing the graph to its actual tail.

        Args:
            right: Branch to extend with.
            tail: Optional tail as a path output vertex.

        Returns: New connected path.
        """
        raise NotImplementedError()

    def subscribe(self, publisher: port.Publishable) -> None:
        """Subscribe head node to given publisher.
        """
        self._head[0].subscribe(publisher)

    @property
    # @abc.abstractmethod
    def publisher(self) -> port.Publishable:
        """Publishable tail node representation.

        Returns: Publishable tail apply port reference.
        """
        raise NotImplementedError()

    def copy(self) -> 'Path':
        """Make a copy of the apply path topology. Any nodes not on path are ignored.

        Returns: Copy of the apply path.
        """

        copies = Traversal(self._head).copy(self._tail)
        return Path(copies[self._head], copies[self._tail])


class Channel(Path):
    """Path with regular output passing data through.
    """

    def extend(self, right: typing.Optional[Path] = None, tail: typing.Optional[grnode.Atomic] = None) -> Path:
        """Create new path by appending right head to our tail or retracing this path up to its physical or specified
        tail.

        Args:
            right: Optional path to extend with (retracing to physical or specified tail if not provided).
            tail: Optional tail as a path output vertex.

        Returns: New extended path.
        """
        # pylint: disable=protected-access
        if right:
            right._head[0].subscribe(self._tail[0])
            if not tail:
                tail = right._tail
        elif not tail:
            tail = Traversal(self._tail).tail().current
        return Path(self._head, tail)

    @property
    def publisher(self) -> port.Publishable:
        """Publishable tail node representation.

        Returns: Publishable tail apply port reference.
        """
        return self._tail[0].publisher


class Closure(Path):
    """Closure is a path with all of its output being published to train port(s) thus not passing anything through.
    Note based on the definition of tail node (having a apply output) this refers to the last apply node before final
    train port subscriber(s).
    """

    class Publishable(port.Publishable):
        """Customized Publishable verifying it's publishing only to Train ports.
        """
        def __init__(self, publisher: port.Publishable):
            super().__init__(None, None)
            self._publisher: port.Publishable = publisher

        def republish(self, subscription: port.Subscription) -> None:
            """Republish the subscription checking it's only for a train port.

            Args:
                subscription: Existing subscription descriptor.
            """
            if isinstance(subscription.port, port.Apply):
                raise graph.Error('Closure path publishing')
            self._publisher.republish(subscription)

    def extend(self, right: typing.Optional[Path] = None, tail: typing.Optional[grnode.Atomic] = None) -> Path:
        """Closure path is not extendable.
        """
        if not right and (not tail or tail == self._tail):
            return Path(self._head, self._tail)
        raise graph.Error('Extending closure path')

    @property
    def publisher(self) -> port.Publishable:
        """Publishable tail node representation. Closure can only be published to Train ports.

        Returns: Publishable tail apply port reference.
        """
        return self.Publishable(self._tail[0].publisher)
