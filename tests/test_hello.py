import time

import pytest


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
    assert True


def test_two():
    assert False

def test_hello(bad_teardown):
    time.sleep(0.05)
    Flakiness.x += 1
    assert Flakiness.x > 0


def test_bye():
    time.sleep(0.05)
    assert False




@pytest.mark.skip
def test_skip():
    assert False

def test_skip4():
    time.sleep(0.05)
    pytest.skip()

def test_blabla():
    assert True
