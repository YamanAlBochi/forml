"""
Project component tests.
"""
# pylint: disable=no-self-use
import typing

import pytest

from forml.project import component as compload


def test_setup():
    """Test the direct setup access.
    """
    with pytest.raises(RuntimeError):
        compload.setup(object())


class TestContext:
    """Context unit tests.
    """
    def test_import(self):
        """Testing the contextual import.
        """
        def handler(instance: typing.Any) -> None:
            """Context handler storing the instance in the enclosing scope.

            Args:
                instance: provided instance to be stored.
            """
            nonlocal provided
            provided = instance

        provided = None
        with compload.Context(handler):
            import component  # component.py in this test directory
            assert provided is component.INSTANCE

        from forml.project import component as compreload
        with pytest.raises(RuntimeError):
            compreload.setup(object())

