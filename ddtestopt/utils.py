import random
from dataclasses import dataclass


def _gen_item_id():
    return random.randint(1, (1<<64) - 1)

@dataclass
class TestContext:
    span_id: int
    trace_id: int
