from functools import wraps
import logging
import typing as t


ddtestopt_logger = logging.getLogger("ddtestopt")

F = t.TypeVar("F", bound=t.Callable[..., t.Any])


def setup_logging():
    ddtestopt_logger.propagate = False
    ddtestopt_logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[Datadog Test Optimization] %(levelname)-8s %(name)s:%(filename)s:%(lineno)d %(message)s")
    )
    ddtestopt_logger.addHandler(handler)


def catch_and_log_exceptions() -> t.Callable[[F], F]:
    def decorator(f: F) -> F:
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception:
                ddtestopt_logger.exception("Error while calling %s", f.__name__)
                return None

        return t.cast(F, wrapper)

    return decorator
