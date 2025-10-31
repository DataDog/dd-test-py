import os
import typing as t

from ddtestpy.internal import ci
from ddtestpy.internal import git
from ddtestpy.internal.ci import CITag
from ddtestpy.internal.git import GitTag
from ddtestpy.internal.utils import _filter_sensitive_info


def get_env_tags() -> t.Dict[str, str]:
    tags = ci.get_ci_tags(os.environ) | git.get_git_tags_from_dd_variables(os.environ)

    # if git.BRANCH is a tag, we associate its value to TAG instead of BRANCH
    if git.is_ref_a_tag(tags.get(GitTag.BRANCH)):
        if not tags.get(GitTag.TAG):
            tags[GitTag.TAG] = git.normalize_ref(tags.get(GitTag.BRANCH))
        else:
            tags[GitTag.TAG] = git.normalize_ref(tags.get(GitTag.TAG))
        del tags[GitTag.BRANCH]
    else:
        tags[GitTag.BRANCH] = git.normalize_ref(tags.get(GitTag.BRANCH))
        tags[GitTag.TAG] = git.normalize_ref(tags.get(GitTag.TAG))

    tags[GitTag.REPOSITORY_URL] = _filter_sensitive_info(tags.get(GitTag.REPOSITORY_URL))

    if workspace_path := tags.get(CITag.WORKSPACE_PATH):
        # DEV: expanduser() requires HOME to be correctly set, so there is no point in accepting the environment as a
        # parameter in this function, the variables have to be in os.environ.
        tags[CITag.WORKSPACE_PATH] = os.path.expanduser(workspace_path)

    return tags
