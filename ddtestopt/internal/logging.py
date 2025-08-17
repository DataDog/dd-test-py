from functools import wraps
import logging


ddtestopt_logger = logging.getLogger("ddtestopt")


def setup_logging():
    ddtestopt_logger.propagate = False
    ddtestopt_logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[Datadog Test Optimization] %(levelname)-8s %(name)s:%(filename)s:%(lineno)d %(message)s")
    )
    ddtestopt_logger.addHandler(handler)


def catch_and_log_exceptions():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception:
                ddtestopt_logger.exception("Error while calling %s", f.__name__)
                return None

        return wrapper

    return decorator
