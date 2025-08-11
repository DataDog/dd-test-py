import time
import pytest

class Flakiness:
    x = 0


def test_hello():
    time.sleep(0.1)
    Flakiness.x += 1
    assert Flakiness.x > 2


@pytest.mark.skip
def test_bye():
    time.sleep(0.1)
    assert False


@pytest.mark.skip
def test_skip():
    time.sleep(0.1)
    assert False
