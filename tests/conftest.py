import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
import pytest
from fastapi.testclient import TestClient
from backend.config import Settings
from backend.main import create_app


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    return create_app(Settings(runtime=tmp_path_factory.mktemp("runtime"), mode="demo"))


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app) as client:
        yield client
