import time

import pytest


class Flakiness:
    x = 0


def test_one():
    assert True


def test_two():
    assert True

def test_hello():
    time.sleep(0.1)
    Flakiness.x += 1
    assert Flakiness.x > 2


def test_bye():
    time.sleep(0.1)
    assert False


def test_skip4():
    time.sleep(0.1)
    pytest.skip()
