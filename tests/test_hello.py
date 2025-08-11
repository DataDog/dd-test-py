import pytest

class Flakiness:
    x = 0


def test_hello():
    Flakiness.x += 1
    assert Flakiness.x > 2


def test_bye():
    assert False


@pytest.mark.skip
def test_skip():
    assert False
