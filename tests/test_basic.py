"""Basic test to ensure the package imports correctly."""

def test_import_ddtestopt():
    """Test that the main package can be imported."""
    import ddtestopt
    assert ddtestopt.__version__ == "0.1.0"


def test_import_internal_modules():
    """Test that internal modules can be imported."""
    from ddtestopt.internal import constants
    from ddtestopt.internal import platform
    from ddtestopt.internal import utils
    
    # Basic smoke tests
    assert hasattr(constants, '__file__')
    assert hasattr(platform, '__file__')
    assert hasattr(utils, '__file__')