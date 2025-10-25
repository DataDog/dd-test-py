import abc
from dataclasses import dataclass
from pathlib import Path
import typing as t


class PushSpanProtocol(t.Protocol):
    def __call__(
        self,
        trace_id: int,
        parent_id: t.Optional[int],
        span_id: int,
        service: str,
        resource: str,
        name: str,
        error: int,
        start_ns: int,
        duration_ns: int,
        meta: t.Dict[str, str],
        metrics: t.Dict[str, float],
        span_type: str,
    ) -> None: ...


@dataclass
class CoverageData:
    bitmaps: t.Dict[str, bytes]


@dataclass
class TraceContext:
    trace_id: int
    span_id: int


class TracerInterface(abc.ABC):
    _instance: t.Optional[t.Type["TracerInterface"]] = None

    @abc.abstractmethod
    def should_enable_test_optimization(self) -> bool: ...

    @abc.abstractmethod
    def should_enable_trace_collection(self) -> bool: ...

    @abc.abstractmethod
    def enable_trace_collection(self, push_span: PushSpanProtocol) -> None: ...

    @abc.abstractmethod
    def disable_trace_collection(self) -> None: ...

    @abc.abstractmethod
    def trace_context(self, resource: str) -> t.ContextManager[TraceContext]: ...

    @abc.abstractmethod
    def enable_coverage_collection(self, workspace_path: Path) -> None: ...

    @abc.abstractmethod
    def disable_coverage_collection(self) -> None: ...

    @abc.abstractmethod
    def coverage_context(self) -> t.ContextManager[CoverageData]: ...


tracer_interface_instance: t.Optional[TracerInterface] = None


def register_tracer_interface(tracer_interface: TracerInterface) -> None:
    global tracer_interface_instance
    tracer_interface_instance = tracer_interface
