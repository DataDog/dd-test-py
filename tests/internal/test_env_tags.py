from collections import Counter
import json
from pathlib import Path
import typing as t

import pytest

from ddtestpy.internal.ci import CITag
from ddtestpy.internal.env_tags import get_env_tags


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "ci"


def _ci_fixtures() -> t.Iterable[t.Tuple[str, int, t.Dict[str, str], t.Dict[str, str]]]:
    for filepath in FIXTURES_DIR.glob("*.json"):
        with open(filepath) as fp:
            for i, [env_vars, expected_tags] in enumerate(json.load(fp)):
                yield filepath.stem, i, env_vars, expected_tags


@pytest.mark.parametrize("name,i,environment,tags", _ci_fixtures())
def test_ci_providers(
    monkeypatch: pytest.MonkeyPatch, name: str, i: int, environment: t.Dict[str, str], tags: t.Dict[str, str]
) -> None:
    """Make sure all provided environment variables from each CI provider are tagged correctly."""
    for k, v in environment.items():
        monkeypatch.setenv(k, v)

    extracted_tags = get_env_tags()
    for key, value in tags.items():
        if key == CITag.NODE_LABELS:
            assert Counter(json.loads(extracted_tags[key])) == Counter(json.loads(value))
        elif key == CITag._CI_ENV_VARS:
            assert json.loads(extracted_tags[key]) == json.loads(value)
        else:
            assert extracted_tags[key] == value, "wrong tags in {0} for {1}".format(name, environment)
