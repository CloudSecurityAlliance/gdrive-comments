"""Session teardown for the live suite: remove the per-run folder.

Separate from the test module because a teardown that lives inside the thing it tears down
runs at import order rather than session end. The folder itself is only created when
`CSA_GW_TEST_FOLDER` is unset — a configured folder is somebody's deliberate scratch space
and is never trashed by a test run.
"""
import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _remove_the_per_run_folder():
    yield
    if os.environ.get("CSA_GW_INTEGRATION") != "1":
        return
    from . import test_all_types_live as suite
    try:
        suite.cleanup_folder(suite._ws())
    except Exception:                            # noqa: BLE001 - never fail a green run here
        pass
