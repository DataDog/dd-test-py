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
    time.sleep(0.1)
    assert True


def test_two():
    time.sleep(0.1)
    assert False

def test_hello():
    time.sleep(0.1)
    Flakiness.x += 1
    assert Flakiness.x > 0


def test_bye():
    time.sleep(0.1)
    assert False




@pytest.mark.skip
def test_skip():
    time.sleep(0.1)
    assert False

def test_skip4():
    time.sleep(0.1)
    pytest.skip()

def test_blabla():
    time.sleep(0.1)
    assert True
