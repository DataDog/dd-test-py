from functools import wraps
import logging
import os
import typing as t

from ddtestopt.internal.utils import asbool


ddtestopt_logger = logging.getLogger("ddtestopt")

F = t.TypeVar("F", bound=t.Callable[..., t.Any])


def setup_logging() -> None:
    ddtestopt_logger.propagate = False

    log_level = logging.DEBUG if asbool(os.getenv("DDTESTOPT_DEBUG")) else logging.INFO
    ddtestopt_logger.setLevel(log_level)

    for handler in list(ddtestopt_logger.handlers):
        ddtestopt_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[Datadog Test Optimization] %(levelname)-8s %(name)s:%(filename)s:%(lineno)d %(message)s")
    )
    ddtestopt_logger.addHandler(handler)


def catch_and_log_exceptions() -> t.Callable[[F], F]:
    def decorator(f: F) -> F:
        @wraps(f)
        def wrapper(*args: t.Any, **kwargs: t.Any) -> t.Any:
            try:
                return f(*args, **kwargs)
            except Exception:
                ddtestopt_logger.exception("Error while calling %s", f.__name__)
                return None

        return t.cast(F, wrapper)

    return decorator
