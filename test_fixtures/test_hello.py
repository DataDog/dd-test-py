import time

import pytest


DELAY = 0.05


@pytest.fixture()
def bad_setup():
    raise Exception("No!")
    yield


@pytest.fixture()
def bad_teardown():
    yield
    raise Exception("No!")


class Flakiness:
    x = 0


def test_one():
    time.sleep(DELAY)
    assert True


def test_two():
    time.sleep(DELAY)
    assert False


def test_hello():
    time.sleep(DELAY)
    Flakiness.x += 1
    assert Flakiness.x > 0


def test_bye():
    time.sleep(DELAY)
    assert False


@pytest.mark.skip
def test_skip():
    time.sleep(DELAY)
    assert False


def test_skip4():
    time.sleep(DELAY)
    pytest.skip()


def test_blabla():
    time.sleep(DELAY)
    assert True


@pytest.mark.parametrize("i", [1, 2])
def test_param(i):
    assert i > 1


def test_param0():
    assert 1 > 1
