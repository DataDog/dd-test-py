from dataclasses import dataclass
import random
import typing as t


DDTESTOPT_ROOT_SPAN_RESOURCE = "ddtestpy_root_span"


def _gen_item_id() -> int:
    return random.randint(1, (1 << 64) - 1)


def asbool(value: t.Union[str, bool, None]) -> bool:
    if value is None:
        return False

    if isinstance(value, bool):
        return value

    return value.lower() in ("true", "1")


@dataclass
class TestContext:
    span_id: int
    trace_id: int
    __test__ = False
