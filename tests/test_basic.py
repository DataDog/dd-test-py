"""Basic test to ensure the package imports correctly."""


def test_import_ddtestopt():
    """Test that the main package can be imported."""
    import ddtestopt

    assert ddtestopt.__version__ == "0.1.0"
