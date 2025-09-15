"""Tests for ddtestopt.internal.writer module."""

import threading
from unittest.mock import Mock
from unittest.mock import patch

from ddtestopt.internal.test_data import TestModule
from ddtestopt.internal.test_data import TestRun
from ddtestopt.internal.test_data import TestSession
from ddtestopt.internal.test_data import TestStatus
from ddtestopt.internal.test_data import TestSuite
from ddtestopt.internal.writer import BaseWriter
from ddtestopt.internal.writer import Event
from ddtestopt.internal.writer import TestCoverageWriter
from ddtestopt.internal.writer import TestOptWriter
from ddtestopt.internal.writer import module_to_event
from ddtestopt.internal.writer import session_to_event
from ddtestopt.internal.writer import suite_to_event
from ddtestopt.internal.writer import test_run_to_event


class TestEvent:
    """Tests for Event class."""

    def test_event_is_dict_subclass(self):
        """Test that Event is a dict subclass."""
        event = Event()
        assert isinstance(event, dict)

    def test_event_creation_with_data(self):
        """Test Event creation with initial data."""
        event = Event(key1="value1", key2="value2")
        assert event["key1"] == "value1"
        assert event["key2"] == "value2"

    def test_event_dict_operations(self):
        """Test that Event supports dict operations."""
        event = Event()
        event["test"] = "data"
        assert event["test"] == "data"
        assert len(event) == 1


class ConcreteWriter(BaseWriter):
    """Concrete implementation of BaseWriter for testing."""

    def __init__(self, site: str, api_key: str):
        super().__init__(site, api_key)
        self.sent_events = []

    def _send_events(self, events):
        self.sent_events.extend(events)


class TestBaseWriter:
    """Tests for BaseWriter abstract base class."""

    def test_base_writer_initialization(self):
        """Test BaseWriter initialization."""
        writer = ConcreteWriter(site="datadoghq.com", api_key="test_key")

        assert writer.site == "datadoghq.com"
        assert writer.api_key == "test_key"
        assert hasattr(writer.lock, "acquire") and hasattr(writer.lock, "release")  # RLock
        assert hasattr(writer.should_finish, "is_set") and hasattr(writer.should_finish, "set")  # Event
        assert writer.flush_interval_seconds == 60
        assert writer.events == []

    def test_put_event(self):
        """Test putting events into the writer."""
        writer = ConcreteWriter(site="test", api_key="key")
        event1 = Event(type="test1")
        event2 = Event(type="test2")

        writer.put_event(event1)
        writer.put_event(event2)

        assert len(writer.events) == 2
        assert writer.events[0] == event1
        assert writer.events[1] == event2

    def test_pop_events(self):
        """Test popping events from the writer."""
        writer = ConcreteWriter(site="test", api_key="key")
        event1 = Event(type="test1")
        event2 = Event(type="test2")

        writer.put_event(event1)
        writer.put_event(event2)

        events = writer.pop_events()

        assert len(events) == 2
        assert events[0] == event1
        assert events[1] == event2
        assert writer.events == []  # Events should be cleared

    def test_pop_events_empty(self):
        """Test popping events when none exist."""
        writer = ConcreteWriter(site="test", api_key="key")
        events = writer.pop_events()
        assert events == []

    def test_thread_safety_put_pop(self):
        """Test thread safety of put_event and pop_events."""
        writer = ConcreteWriter(site="test", api_key="key")

        def add_events():
            for i in range(100):
                writer.put_event(Event(index=i))

        # Start multiple threads adding events
        threads = [threading.Thread(target=add_events) for _ in range(3)]
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should have 300 events total
        events = writer.pop_events()
        assert len(events) == 300

    def test_flush_with_events(self):
        """Test flush method with events."""
        writer = ConcreteWriter(site="test", api_key="key")
        event1 = Event(type="test1")
        event2 = Event(type="test2")

        writer.put_event(event1)
        writer.put_event(event2)

        writer.flush()

        # Events should be sent and cleared
        assert writer.sent_events == [event1, event2]
        assert writer.events == []

    def test_flush_without_events(self):
        """Test flush method without events."""
        writer = ConcreteWriter(site="test", api_key="key")

        writer.flush()

        # No events should be sent
        assert writer.sent_events == []

    @patch("threading.Thread")
    def test_start(self, mock_thread_class):
        """Test starting the background thread."""
        mock_thread = Mock()
        mock_thread_class.return_value = mock_thread

        writer = ConcreteWriter(site="test", api_key="key")
        writer.start()

        mock_thread_class.assert_called_once_with(target=writer._periodic_task)
        mock_thread.start.assert_called_once()
        assert writer.task == mock_thread

    def test_finish(self):
        """Test finishing the writer."""
        writer = ConcreteWriter(site="test", api_key="key")
        writer.task = Mock()

        writer.finish()

        assert writer.should_finish.is_set()
        writer.task.join.assert_called_once()

    def test_periodic_task_loop(self):
        """Test the periodic task loop."""
        writer = ConcreteWriter(site="test", api_key="key")

        # Mock the should_finish event to break after first iteration
        writer.should_finish.is_set = Mock(return_value=True)  # Exit immediately after first flush
        writer.should_finish.wait = Mock()

        with patch.object(writer, "flush") as mock_flush:
            writer._periodic_task()

        # Should wait for flush interval and call flush once
        writer.should_finish.wait.assert_called_with(timeout=60)
        mock_flush.assert_called_once()


class TestTestOptWriter:
    """Tests for TestOptWriter class."""

    @patch("ddtestopt.internal.writer.BackendConnector")
    def test_testopt_writer_initialization(self, mock_backend_connector):
        """Test TestOptWriter initialization."""
        mock_connector = Mock()
        mock_backend_connector.return_value = mock_connector

        writer = TestOptWriter(site="datadoghq.com", api_key="test_key")

        assert writer.site == "datadoghq.com"
        assert writer.api_key == "test_key"
        assert writer.connector == mock_connector

        # Check metadata structure
        assert "language" in writer.metadata["*"]
        assert writer.metadata["*"]["language"] == "python"
        assert "_dd.origin" in writer.metadata["*"]

        # Check test capabilities
        assert "_dd.library_capabilities.early_flake_detection" in writer.metadata["test"]

        # Check serializers
        assert TestRun in writer.serializers
        assert TestSuite in writer.serializers
        assert TestModule in writer.serializers
        assert TestSession in writer.serializers

    @patch("ddtestopt.internal.writer.BackendConnector")
    def test_add_metadata(self, mock_backend_connector):
        """Test adding metadata to writer."""
        writer = TestOptWriter(site="test", api_key="key")

        writer.add_metadata("test", {"custom.key": "custom_value"})

        assert writer.metadata["test"]["custom.key"] == "custom_value"

    @patch("ddtestopt.internal.writer.BackendConnector")
    def test_put_item(self, mock_backend_connector):
        """Test putting a test item."""
        writer = TestOptWriter(site="test", api_key="key")

        # Create a mock test run
        test_run = Mock(spec=TestRun)
        test_run.__class__ = TestRun

        # Mock the serializer
        with patch.object(writer, "serializers") as mock_serializers:
            mock_serializer = Mock(return_value=Event(type="test"))
            mock_serializers.__getitem__.return_value = mock_serializer

            writer.put_item(test_run)

            mock_serializer.assert_called_once_with(test_run)
            assert len(writer.events) == 1

    @patch("ddtestopt.internal.writer.BackendConnector")
    @patch("msgpack.packb")
    def test_send_events(self, mock_packb, mock_backend_connector):
        """Test sending events to backend."""
        mock_connector = Mock()
        mock_backend_connector.return_value = mock_connector
        # Make sure request returns a tuple like the real implementation
        mock_connector.request.return_value = (Mock(), {})
        mock_packb.return_value = b"packed_data"

        writer = TestOptWriter(site="test", api_key="key")
        events = [Event(type="test1"), Event(type="test2")]

        writer._send_events(events)

        # Check msgpack packaging
        expected_payload = {
            "version": 1,
            "metadata": writer.metadata,
            "events": events,
        }
        mock_packb.assert_called_once_with(expected_payload)

        # Check HTTP request
        mock_connector.request.assert_called_once_with(
            "POST",
            "/api/v2/citestcycle",
            data=b"packed_data",
            headers={"Content-Type": "application/msgpack"},
            send_gzip=True,
        )


class TestTestCoverageWriter:
    """Tests for TestCoverageWriter class."""

    @patch("ddtestopt.internal.writer.BackendConnector")
    def test_coverage_writer_initialization(self, mock_backend_connector):
        """Test TestCoverageWriter initialization."""
        mock_connector = Mock()
        mock_backend_connector.return_value = mock_connector

        writer = TestCoverageWriter(site="datadoghq.com", api_key="test_key")

        assert writer.site == "datadoghq.com"
        assert writer.api_key == "test_key"
        assert writer.connector == mock_connector

        # Check connector initialization
        mock_backend_connector.assert_called_once_with(
            host="citestcov-intake.datadoghq.com", default_headers={"dd-api-key": "test_key"}
        )

    @patch("ddtestopt.internal.writer.BackendConnector")
    def test_put_coverage(self, mock_backend_connector):
        """Test putting coverage data."""
        writer = TestCoverageWriter(site="test", api_key="key")

        # Mock test run
        test_run = Mock()
        test_run.session_id = 123
        test_run.suite_id = 456
        test_run.span_id = 789

        # Mock coverage data
        mock_coverage1 = Mock()
        mock_coverage1.to_bytes.return_value = b"coverage1_bytes"
        mock_coverage2 = Mock()
        mock_coverage2.to_bytes.return_value = b"coverage2_bytes"

        coverage_data = {
            "file1.py": mock_coverage1,
            "file2.py": mock_coverage2,
        }

        writer.put_coverage(test_run, coverage_data)

        # Check event was created and added
        assert len(writer.events) == 1
        event = writer.events[0]
        assert event["test_session_id"] == 123
        assert event["test_suite_id"] == 456
        assert event["span_id"] == 789
        assert len(event["files"]) == 2

    @patch("ddtestopt.internal.writer.BackendConnector")
    @patch("msgpack.packb")
    def test_send_coverage_events(self, mock_packb, mock_backend_connector):
        """Test sending coverage events."""
        mock_connector = Mock()
        mock_backend_connector.return_value = mock_connector
        # Make sure post_files returns a tuple like the real implementation
        mock_connector.post_files.return_value = (Mock(), {})
        mock_packb.return_value = b"packed_coverage_data"

        writer = TestCoverageWriter(site="test", api_key="key")
        events = [Event(type="coverage1"), Event(type="coverage2")]

        writer._send_events(events)

        # Check msgpack packaging
        mock_packb.assert_called_once_with({"version": 2, "coverages": events})

        # Check file attachment structure
        mock_connector.post_files.assert_called_once()
        call_args = mock_connector.post_files.call_args

        assert call_args[0][0] == "/api/v2/citestcov"
        files = call_args[1]["files"]
        assert len(files) == 2
        assert files[0].name == "coverage1"
        assert files[0].content_type == "application/msgpack"
        assert files[1].name == "event"
        assert files[1].content_type == "application/json"
        assert call_args[1]["send_gzip"] is True


class TestSerializationFunctions:
    """Tests for event serialization functions."""

    def create_mock_test_run(self):
        """Create a mock TestRun with required attributes."""
        test_run = Mock(spec=TestRun)
        test_run.trace_id = 111
        test_run.span_id = 222
        test_run.service = "test_service"
        test_run.name = "test_function"
        test_run.start_ns = 1000000000
        test_run.duration_ns = 500000000
        test_run.session_id = 333
        test_run.module_id = 444
        test_run.suite_id = 555
        test_run.tags = {"custom.tag": "value"}
        test_run.metrics = {"custom.metric": 42}

        # Mock the nested parent structure: TestRun -> TestSuite -> TestModule -> TestSession
        test_run.parent = Mock()  # TestSuite
        test_run.parent.tags = {"suite.tag": "suite_value"}
        test_run.parent.parent = Mock()  # TestModule
        test_run.parent.parent.name = "TestClass"  # test.suite
        test_run.parent.parent.parent = Mock()  # TestSession
        test_run.parent.parent.parent.name = "test_session"  # test.module
        test_run.parent.parent.parent.module_path = "/path/to/test_module.py"

        test_run.get_status.return_value = TestStatus.PASS

        return test_run

    def test_test_run_to_event_pass(self):
        """Test serializing a passing test run."""
        test_run = self.create_mock_test_run()
        test_run.get_status.return_value = TestStatus.PASS

        event = test_run_to_event(test_run)

        assert event["version"] == 2
        assert event["type"] == "test"
        assert event["content"]["trace_id"] == 111
        assert event["content"]["span_id"] == 222
        assert event["content"]["service"] == "test_service"
        assert event["content"]["resource"] == "test_function"
        assert event["content"]["name"] == "pytest.test"
        assert event["content"]["error"] == 0  # Pass = no error
        assert event["content"]["start"] == 1000000000
        assert event["content"]["duration"] == 500000000

        # Check metadata
        meta = event["content"]["meta"]
        assert meta["span.kind"] == "test"
        assert meta["test.name"] == "test_function"
        assert meta["test.status"] == "pass"
        assert meta["test.suite"] == "TestClass"
        assert meta["test.module"] == "test_session"
        assert meta["test.module_path"] == "/path/to/test_module.py"
        assert meta["custom.tag"] == "value"
        assert meta["suite.tag"] == "suite_value"

        # Check metrics
        metrics = event["content"]["metrics"]
        assert metrics["_dd.py.partial_flush"] == 1
        assert metrics["custom.metric"] == 42

    def test_test_run_to_event_fail(self):
        """Test serializing a failing test run."""
        test_run = self.create_mock_test_run()
        test_run.get_status.return_value = TestStatus.FAIL

        event = test_run_to_event(test_run)

        assert event["content"]["error"] == 1  # Fail = error
        assert event["content"]["meta"]["test.status"] == "fail"

    def create_mock_test_suite(self):
        """Create a mock TestSuite."""
        suite = Mock(spec=TestSuite)
        suite.service = "test_service"
        suite.name = "TestSuite"
        suite.start_ns = 2000000000
        suite.duration_ns = 1500000000
        suite.session_id = 666
        suite.module_id = 777
        suite.suite_id = 888
        suite.tags = {"suite.custom": "suite_value"}
        suite.metrics = {"suite.metric": 100}
        suite.get_status.return_value = TestStatus.PASS
        return suite

    def test_suite_to_event(self):
        """Test serializing a test suite."""
        suite = self.create_mock_test_suite()

        event = suite_to_event(suite)

        assert event["version"] == 1
        assert event["type"] == "test_suite_end"
        assert event["content"]["service"] == "test_service"
        assert event["content"]["resource"] == "TestSuite"
        assert event["content"]["name"] == "pytest.test_suite"
        assert event["content"]["error"] == 0
        assert event["content"]["start"] == 2000000000
        assert event["content"]["duration"] == 1500000000

        # Check metadata
        meta = event["content"]["meta"]
        assert meta["span.kind"] == "test"
        assert meta["test.suite"] == "TestSuite"
        assert meta["test.status"] == "pass"
        assert meta["type"] == "test_suite_end"
        assert meta["suite.custom"] == "suite_value"

        # Check the correlation ID is present
        assert "itr_correlation_id" in event["content"]

    def create_mock_test_module(self):
        """Create a mock TestModule."""
        module = Mock(spec=TestModule)
        module.service = "test_service"
        module.name = "test_module"
        module.module_path = "/path/to/test_module.py"
        module.start_ns = 3000000000
        module.duration_ns = 2500000000
        module.session_id = 999
        module.module_id = 1111
        module.tags = {"module.custom": "module_value"}
        module.metrics = {"module.metric": 200}
        module.get_status.return_value = TestStatus.SKIP
        return module

    def test_module_to_event(self):
        """Test serializing a test module."""
        module = self.create_mock_test_module()

        event = module_to_event(module)

        assert event["version"] == 1
        assert event["type"] == "test_module_end"
        assert event["content"]["service"] == "test_service"
        assert event["content"]["resource"] == "test_module"
        assert event["content"]["name"] == "pytest.test_module"
        assert event["content"]["error"] == 0
        assert event["content"]["start"] == 3000000000
        assert event["content"]["duration"] == 2500000000

        # Check metadata
        meta = event["content"]["meta"]
        assert meta["span.kind"] == "test"
        assert meta["test.module"] == "test_module"
        assert meta["test.module_path"] == "/path/to/test_module.py"
        assert meta["test.status"] == "skip"
        assert meta["type"] == "test_module_end"
        assert meta["module.custom"] == "module_value"

    def create_mock_test_session(self):
        """Create a mock TestSession."""
        session = Mock(spec=TestSession)
        session.service = "test_service"
        session.name = "test_session"
        session.start_ns = 4000000000
        session.duration_ns = 3500000000
        session.session_id = 2222
        session.tags = {"session.custom": "session_value"}
        session.metrics = {"session.metric": 300}
        session.get_status.return_value = TestStatus.FAIL
        return session

    def test_session_to_event(self):
        """Test serializing a test session."""
        session = self.create_mock_test_session()

        event = session_to_event(session)

        assert event["version"] == 1
        assert event["type"] == "test_session_end"
        assert event["content"]["service"] == "test_service"
        assert event["content"]["resource"] == "test_session"
        assert event["content"]["name"] == "pytest.test_session"
        assert event["content"]["error"] == 0
        assert event["content"]["start"] == 4000000000
        assert event["content"]["duration"] == 3500000000

        # Check metadata
        meta = event["content"]["meta"]
        assert meta["span.kind"] == "test"
        assert meta["test.status"] == "fail"
        assert meta["type"] == "test_session_end"
        assert meta["session.custom"] == "session_value"

        # Check metrics include top level
        metrics = event["content"]["metrics"]
        assert metrics["_dd.top_level"] == 1
        assert metrics["session.metric"] == 300
