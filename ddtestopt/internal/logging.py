from functools import wraps
import logging
import typing as t


ddtestopt_logger = logging.getLogger("ddtestopt")


def setup_logging():
    ddtestopt_logger.propagate = False
    ddtestopt_logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[Datadog Test Optimization] %(levelname)-8s %(name)s:%(filename)s:%(lineno)d %(message)s")
    )
    ddtestopt_logger.addHandler(handler)


TCallable = t.TypeVar("TCallable", bound=t.Callable[..., t.Any])


class catch_and_log_exceptions:
    """
    A class that can be used either as a context manager or a decorator to catch and log exceptions.

    As a decorator, it can be used like:

        @catch_and_log_exceptions()
        def some_function(x):
            raise Exception("this will be caught and the function will return None")

    As a context manager, it can be used like:

        with catch_and_log_exceptions():
            raise Exception("this will be caught and execution will continue after the block")

        print("this will run normally")

    """
    def __init__(self, name: str = "<block>") -> None:
        self.name = name

    def __enter__(self) -> None:
        pass

    def __exit__(self,  exc_type, exc_value, traceback) -> t.Optional[bool]:
        if exc_value is not None:
            ddtestopt_logger.error("Error while calling %s", self.name, exc_info=(exc_type, exc_value, traceback))
            return True  # suppress exception in context handler

    def __call__(self, f: TCallable) -> TCallable:
        """
        Allow the instance to be used as a decorator, wrapping calls to the function in a `catch_and_log_exceptions`
        context.
        """
        @wraps(f)
        def wrapper(*args, **kwargs):
            with self:
                return f(*args, **kwargs)

        self.name = f.__name__
        return t.cast(TCallable, wrapper)
