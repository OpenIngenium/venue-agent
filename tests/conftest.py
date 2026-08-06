import tests._jwt_env
import os
import time
import subprocess
from pathlib import Path
import datetime
import logging
from unittest.mock import patch
import fakeredis


import pytest
import requests
import jwt  # PyJWT – add to requirements if not already present
from fastapi.testclient import TestClient

# ----------------------------------------------------------------------
# Import the FastAPI app **after** the environment is prepared.
# ----------------------------------------------------------------------
from main import app

# ----------------------------------------------------------------------
# NEW: configure application logging to a temporary file
# ----------------------------------------------------------------------
@pytest.fixture(scope="function", autouse=True)
def per_test_logging(request, tmp_path):
    """
    Create a temporary log file for the *current* test case and attach a
    ``FileHandler`` to the root logger (or the specific logger used by the
    application). The handler is removed after the test finishes.

    The fixture yields the :class:`pathlib.Path` of the log file so a test can
    read it if desired, but it also runs automatically for every test because
    ``autouse=True``.
    """
    # ------------------------------------------------------------------
    # 1️⃣ Build a safe filename from the test's nodeid.
    # ------------------------------------------------------------------
    # ``nodeid`` looks like "tests/test_custom_script.py::test_start_custom_script_success"
    # Replace characters that are illegal in filenames.
    safe_name = request.node.nodeid.replace("/", "_").replace("::", "__")
    safe_name = safe_name.replace("[", "_").replace("]", "_")
    log_file = tmp_path / f"{safe_name}.log"

    # ------------------------------------------------------------------
    # 2️⃣ Set up a file handler on the logger used by the app.
    # ------------------------------------------------------------------
    # If your application uses a dedicated logger (e.g., `logging.getLogger("venue_server")`),
    # replace `logging.getLogger()` with that name.
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)   # capture everything; adjust as needed

    file_handler = logging.FileHandler(log_file, mode="w")
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # ------------------------------------------------------------------
    # 3️⃣ Yield the path for optional test‑side inspection.
    # ------------------------------------------------------------------
    yield log_file


@pytest.fixture(scope="session")
def jwt_token():
    """
    Returns a JWT signed with the *private* RSA key.  The server validates it
    with the public key that was placed in ``JWT_SECRET`` above.
    """
    # The private key is read from the file set in ``JWT_PRIVATE_KEY``.
    private_key_path = os.getenv("JWT_PRIVATE_KEY")
    assert private_key_path, "JWT_PRIVATE_KEY env var not set"
    private_key = Path(private_key_path).read_text()
    algorithm = os.getenv("JWT_ALGORITHM", "RS256")

    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    payload = {
        "sub": "test_user",            # subject – can be any identifier
        "iat": now_ts,                    # issued‑at
        "exp": now_ts + 3600,  # expires in 1 hour
        "iss": "test_suite",
        "scopes": [{"scope": "execute:testbed"}]
    }

    token = jwt.encode(payload, private_key, algorithm=algorithm)

    # PyJWT 2.x returns ``str``; older versions return ``bytes``.
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


@pytest.fixture(scope="session")
def expired_jwt_token():
    """
    Returns a JWT signed with the *private* RSA key.  The server validates it
    with the public key that was placed in ``JWT_SECRET`` above.
    """
    # The private key is read from the file set in ``JWT_PRIVATE_KEY``.
    private_key_path = os.getenv("JWT_PRIVATE_KEY")
    assert private_key_path, "JWT_PRIVATE_KEY env var not set"
    private_key = Path(private_key_path).read_text()
    algorithm = os.getenv("JWT_ALGORITHM", "RS256")

    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    payload = {
        "sub": "test_user",            # subject – can be any identifier
        "iat": now_ts,                    # issued‑at
        "exp": now_ts + 3600,  # expires in 1 hour
        "iss": "test_suite",
        "scopes": [{}]
    }

    token = jwt.encode(payload, private_key, algorithm=algorithm)

    # PyJWT 2.x returns ``str``; older versions return ``bytes``.
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


@pytest.fixture(scope="session")
def no_scope_jwt_token():
    """
    Returns a JWT signed with the *private* RSA key.  The server validates it
    with the public key that was placed in ``JWT_SECRET`` above.
    """
    # The private key is read from the file set in ``JWT_PRIVATE_KEY``.
    private_key_path = os.getenv("JWT_PRIVATE_KEY")
    assert private_key_path, "JWT_PRIVATE_KEY env var not set"
    private_key = Path(private_key_path).read_text()
    algorithm = os.getenv("JWT_ALGORITHM", "RS256")

    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    payload = {
        "sub": "test_user",            # subject – can be any identifier
        "iat": now_ts - 7200,          # issued 2 h ago
        "exp": now_ts - 3600,          # expired 1 h ago
        "iss": "test_suite",
        "scopes": [{"scope": "execute:testbed"}]
    }

    token = jwt.encode(payload, private_key, algorithm=algorithm)

    # PyJWT 2.x returns ``str``; older versions return ``bytes``.
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token

@pytest.fixture(scope="session", autouse=True)
def fake_redis():
    """Patch redis.Redis with a shared FakeRedis server for the entire test session."""
    server = fakeredis.FakeServer()
    with patch("redis.Redis", lambda *args, **kwargs: fakeredis.FakeRedis(server=server)):
        yield server


@pytest.fixture(scope="module")
def auth_client(jwt_token):
    """
    Returns a TestClient that runs the FastAPI app locally and includes the
    Bearer token in the `Authorization` header for every request.
    """
    with TestClient(app) as c:
        # Set default headers for the client instance.
        c.headers.update({"Authorization": f"Bearer {jwt_token}"})
        yield c


