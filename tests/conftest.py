"""Every test run keeps the app's data folder (settings, fleet / depot / stabling lists, error.log) in a temporary
folder, so tests never change a real user's data folder. Tests that need their own folder still set LOCALAPPDATA."""
import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _private_data_folder(tmp_path_factory):
    old = {k: os.environ.get(k) for k in ("LOCALAPPDATA", "APPDATA")}
    folder = str(tmp_path_factory.mktemp("appdata"))
    os.environ["LOCALAPPDATA"] = os.environ["APPDATA"] = folder
    try:
        yield folder
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
