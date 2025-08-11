import os
import typing as t
import uuid

import msgpack
import requests


class Event(dict):
    pass


class TestOptWriter:
    def __init__(self):
        self.events: t.List[Event] = []
        self.metadata: t.Dict[str, t.Dict[str, str]] = {
            "*": {
                "language": "python",
                "runtime-id": uuid.uuid4().hex,
                "library_version": "0.0.0",
                "_dd.origin": "ciapp-test",
                "_dd.p.dm": "-0",  # what is this?
            },
        }
        self.api_key = os.environ["DD_API_KEY"]

    def append_event(self, event: Event) -> None:
        self.events.append(event)

    def add_metadata(self, event_type: str, metadata: t.Dict[str, str]) -> None:
        self.metadata[event_type].update(metadata)

    def send(self):
        payload = {
            "version": 1,
            "metadata": self.metadata,
            "events": self.events,
        }
        breakpoint()
        pack = msgpack.packb(payload)
        url = "https://citestcycle-intake.datadoghq.com/api/v2/citestcycle"
        # url = "https://citestcycle-intake.datad0g.com/api/v2/citestcycle"
        response = requests.post(
            url,
            data=pack,
            headers={
                "content-type": "application/msgpack",
                "dd-api-key": self.api_key,
            },
        )
        print(response)
