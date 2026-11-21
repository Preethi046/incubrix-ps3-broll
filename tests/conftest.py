import pytest
from fastapi.testclient import TestClient
from broll.api import create_app
from broll.config import Settings

@pytest.fixture
def settings(tmp_path): return Settings(data_dir=tmp_path,database=tmp_path/"jobs.db",catalog=tmp_path/"catalog.json",_env_file=None)
@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client: yield client
