"""
dd-trace-py interaction layer.
"""
import contextlib
import logging
from ddtestopt.utils import _gen_item_id, TestContext

log = logging.getLogger(__name__)

def install_global_trace_filter(writer):
    try:
        import ddtrace
    except ImportError:
        log.debug("ddrace is not available, not installing trace filter")
        return None

    from .span_processor import TestOptSpanProcessor

    try:
        ddtrace.tracer.configure(trace_processors=[TestOptSpanProcessor(writer)])
    except TypeError:
        # ddtrace 2.x compatibility
        ddtrace.tracer.configure(settings={'FILTERS': [TestOptSpanProcessor(writer)]})

    ddtrace.patch(flask=True)


def uninstall_global_trace_filter():
    try:
        import ddtrace
    except ImportError:
        return None

    try:
        ddtrace.tracer.configure(trace_processors=[])
    except TypeError:
        # ddtrace 2.x compatibility
        ddtrace.tracer.configure(settings={'FILTERS': []})


def trace_context(ddtrace_enabled: bool):
    if ddtrace_enabled:
        try:
            import ddtrace
            return _ddtrace_context()
        except ImportError:
            log.debug("ddrace is not available, falling back to non-ddtrace context")

    return _plain_context()



@contextlib.contextmanager
def _ddtrace_context():
    import ddtrace
    with ddtrace.tracer.trace("ddtestopt") as root_span:
        yield TestContext(trace_id=root_span.trace_id % (1<<64), span_id=root_span.span_id % (1<<64))


@contextlib.contextmanager
def _plain_context():
    yield TestContext(trace_id=_gen_item_id(), span_id=_gen_item_id())
