import pytest


def test_hello():
    assert True


def test_bye():
    assert False


@pytest.mark.skip
def test_skip():
    assert False
