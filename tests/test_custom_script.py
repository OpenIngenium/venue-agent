"""
Test suite for /api/v3/custom_script/
"""

import hashlib
import time
import shutil
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app


def _sha256(file_path: Path) -> str:
    """Return the SHA‑256 hash of *file_path* as a hex string."""
    hasher = hashlib.sha256()
    hasher.update(file_path.read_bytes())
    return hasher.hexdigest()

@pytest.mark.timeout(15)
def test_start_custom_script_success(auth_client: TestClient):
    """
    Nominal test for /api/v3/custom_script/start
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"


@pytest.mark.timeout(35)
def test_start_custom_script_abs_path(auth_client: TestClient):
    """
    Off-nominal test for /api/v3/custom_script/start (bad path)

    This ensures that the custom script functionality only works on relative path (so within the base dir)
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    tmp_path = Path("/tmp/venue_agent_test/custom_script_for_tests.py")

    os.makedirs('/tmp/venue_agent_test', exist_ok=True)

    shutil.copyfile(script_path, tmp_path)
    os.chmod(tmp_path, 0o777)
    assert tmp_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": str(tmp_path),
        "scriptHash": _sha256(tmp_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 400, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(35)
def test_start_custom_script_rel_bad_path(auth_client: TestClient):
    """
    Off-nominal test for /api/v3/custom_script/start (bad relative path)

    This ensures that the custom script functionality only works on a path that does not include ".."
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    tmp_path = Path("../../../../../tmp/venue_agent_test/custom_script_for_tests.py")

    os.makedirs('/tmp/venue_agent_test', exist_ok=True)

    shutil.copyfile(script_path, tmp_path)
    os.chmod(tmp_path, 0o777)
    assert tmp_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": str(tmp_path),
        "scriptHash": _sha256(tmp_path),
        "inputs": inputs,  # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 400, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(35)
def test_start_custom_script_home_bad_path(auth_client: TestClient):
    """
    Off-nominal test for /api/v3/custom_script/start (home directory)

    This ensures that the custom script functionality does not operate with paths point to the home directory
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    tmp_path = Path("~/tmp/venue_agent_test/custom_script_for_tests.py")

    if not os.path.exists('~/tmp/venue_agent_test'):
        os.makedirs('~/tmp/venue_agent_test/', exist_ok=True)

    shutil.copyfile(script_path, tmp_path)
    os.chmod(tmp_path, 0o777)
    assert tmp_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": str(tmp_path),
        "scriptHash": _sha256(tmp_path),
        "inputs": inputs,  # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 400, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(15)
def test_start_custom_script_not_present(auth_client: TestClient):
    """
    Off-nominal test for /api/v3/custom_script/start
    For the scenario where the custom script is not located in the specific path
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "not_present.py"
    assert not script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "not_present",
        "scriptPath": "custom_script_for_tests/not_present.py",
        "scriptHash": "nohashneededsincefiledoesnotexist",
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 400, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(15)
def test_start_custom_script_badhash(auth_client: TestClient):
    """
    Off-nominal test for /api/v3/custom_script/start
    For the scenario where the provided hash does not match
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": "thishashisnotvalidforanything",
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 400, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(35)
def test_status_custom_script_pass(auth_client: TestClient):
    """
    Nominal test for /api/v3/custom_script/start and /api/v3/custom_script/
    This scenario tests a custom script running until is flags itself complete
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    script_run_id = data["scriptRunId"]

    script_status = ""

    while script_status != "PASS":
        response = auth_client.get(f"/api/v3/custom_script/{script_run_id}")

        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        data = response.json()

        script_status = data["custom_script_status"]
        time.sleep(1)

    assert script_status == "PASS", (f"Unexpected script completion status {script_status}")


@pytest.mark.timeout(35)
def test_status_custom_script_exception(auth_client: TestClient):
    """
    Off-nominal test for /api/v3/custom_script/start and /api/v3/custom_script/
    For the scenario where a custom script encounters an exception while executing
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS',
                         'exception_time': 10}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    script_run_id = data["scriptRunId"]

    script_status = ""

    while script_status != "ERROR":
        response = auth_client.get(f"/api/v3/custom_script/{script_run_id}")

        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        data = response.json()

        script_status = data["custom_script_status"]
        time.sleep(1)

    assert script_status == "ERROR", (f"Unexpected script completion status {script_status}")


@pytest.mark.timeout(60)
def test_custom_script_halt(auth_client: TestClient):
    """
    Nominal test for /api/v3/custom_script/start, /api/v3/custom_script/ and /api/v3/custom_script/halt
    This scenario captures a custom script starting, being status'd and then halted
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 60,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    time.sleep(10)

    script_run_id = data["scriptRunId"]

    script_status = ""

    while script_status != "PENDING":
        response = auth_client.get(f"/api/v3/custom_script/{script_run_id}")

        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        data = response.json()

        script_status = data["custom_script_status"]
        time.sleep(1)

    assert script_status == "PENDING", (f"Unexpected script completion status {script_status}")

    response = auth_client.post(f"/api/v3/custom_script/{script_run_id}/halt")

    assert response.status_code == 204, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(30)
def test_custom_script_halt_completed_script(auth_client: TestClient):
    """
    Nominal test for /api/v3/custom_script/start, /api/v3/custom_script/ and /api/v3/custom_script/halt
    For the scenario where the custom script runs to completion and is then halted
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 10,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    script_run_id = data["scriptRunId"]

    script_status = ""

    while script_status != "PASS":
        response = auth_client.get(f"/api/v3/custom_script/{script_run_id}")

        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        data = response.json()

        script_status = data["custom_script_status"]
        time.sleep(1)

    assert script_status == "PASS", (f"Unexpected script completion status {script_status}")

    response = auth_client.post(f"/api/v3/custom_script/{script_run_id}/halt")

    assert response.status_code == 204, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(10)
def test_halt_custom_script_invalid_id(auth_client: TestClient):
    """
    Off-nominal test for /api/v3/custom_script/halt
    For the scenario where halt is executed on a script id that doesn't exist
    """

    script_run_id = "InvalidID"

    response = auth_client.post(f"/api/v3/custom_script/{script_run_id}/halt")

    assert response.status_code == 400, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(35)
def test_custom_script_large_response(auth_client: TestClient):
    """
    Stress test for /api/v3/custom_script/start, /api/v3/custom_script/
    A scenario where the custom script generates significant (10MB) data
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS',
                         "output_random_data": 1000000}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    time.sleep(20)

    script_run_id = data["scriptRunId"]

    script_status = ""

    while script_status != "PASS":
        response = auth_client.get(f"/api/v3/custom_script/{script_run_id}")

        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        data = response.json()

        script_status = data["custom_script_status"]
        time.sleep(1)

    assert script_status == "PASS", f"Unexpected script completion status {script_status}"


@pytest.mark.timeout(45)
def test_custom_script_files(auth_client: TestClient):
    """
    Nominal test for /api/v3/custom_script/start, /api/v3/custom_script/, and /api/v3/custom_script/files
    Runs a custom script to completion and then retrieves the file
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS',
                         "output_random_data": 1000000}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    script_run_id = data["scriptRunId"]

    script_status = ""

    while script_status != "PASS":
        response = auth_client.get(f"/api/v3/custom_script/{script_run_id}")

        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        data = response.json()

        script_status = data["custom_script_status"]
        time.sleep(1)

    assert script_status == "PASS", (f"Unexpected script completion status {script_status}")

    files = auth_client.get(f"/api/v3/custom_script/{script_run_id}/files")

    assert files.status_code == 200, f"Unexpected status {files.status_code}: {files.text}"


@pytest.mark.timeout(45)
def test_custom_script_files_bad_id(auth_client: TestClient):
    """
    Off-nominal test for /api/v3/custom_script/files
    For the scenario where the files endpoint is exercised on a id that doesn't exist
    """

    script_run_id = "NOT FOUND"
    files = auth_client.get(f"/api/v3/custom_script/{script_run_id}/files")

    assert files.status_code == 400, f"Unexpected status {files.status_code}: {files.text}"


@pytest.mark.timeout(100)
def test_custom_script_heavy_writes_limited_wait(auth_client: TestClient):
    """
    This is a stress test where the custom script generates a lot of data (10MB) and saves it rapidly (10Hz) and polls
    it rapidly (2Hz). This ensures that the retry functionality (if the output.json file is being written) is working.
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 90,
                         'script_result': 'PASS',
                         'heavy_writes' : 'true',
                         "output_random_data": 10000000}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}    # No predefined outputs.
    }


    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    script_run_id = data["scriptRunId"]

    script_status = ""

    while script_status != "PASS":
        response = auth_client.get(f"/api/v3/custom_script/{script_run_id}")

        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        data = response.json()

        script_status = data["custom_script_status"]

        time.sleep(0.5)

    assert script_status == "PASS", (f"Unexpected script completion status {script_status}")


def test_start_custom_script_expired(auth_client: TestClient, expired_jwt_token):
    """
    Off-nominal test for /api/v3/custom_script/start
    With an expired JWT Token
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload, headers={"Authorization": f"Bearer {expired_jwt_token}"})

    assert response.status_code == 403, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


def test_start_custom_script_unauthorized(auth_client, no_scope_jwt_token):
    """
    Off-nominal test for /api/v3/custom_script/start
    With a JWT Token that lackes the permissions
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload, headers={"Authorization": f"Bearer {no_scope_jwt_token}"})

    assert response.status_code == 401, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


def test_start_custom_script_no_header(auth_client: TestClient):
    """
    Off-nominal test for /api/v3/custom_script/start
    With a missing JWT token/header
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload, headers={"Authorization": "notatoken"})

    assert response.status_code == 401, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


def test_start_custom_script_no_name(auth_client: TestClient):
    """
    Off-nominal test for /api/v3/custom_script/start
    Without a scriptName
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 400, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


def test_start_custom_script_no_path(auth_client: TestClient):
    """
    Off-nominal test for /api/v3/custom_script/start
    Without a scriptPath
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 400, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


def test_start_custom_script_no_hash(auth_client: TestClient):
    """
    Off-nominal test for /api/v3/custom_script/start
    Without a scriptHash field
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 400, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(35)
def test_status_custom_script_expired(auth_client: TestClient, expired_jwt_token):
    """
    Off-nominal test for /api/v3/custom_script/
    With an expired JWT Token
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    script_run_id = data["scriptRunId"]

    script_status = ""

    response = auth_client.get(f"/api/v3/custom_script/{script_run_id}", headers={"Authorization": f"Bearer {expired_jwt_token}"})

    assert response.status_code == 403, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(35)
def test_status_custom_script_unauthorized(auth_client: TestClient, no_scope_jwt_token):
    """
    Off-nominal test for /api/v3/custom_script/
    With a JWT Token without the correct permissions
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,  # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    script_run_id = data["scriptRunId"]

    script_status = ""

    response = auth_client.get(f"/api/v3/custom_script/{script_run_id}",
                               headers={"Authorization": f"Bearer {no_scope_jwt_token}"})

    assert response.status_code == 401, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(60)
def test_custom_script_halt_unauthorized(auth_client: TestClient, no_scope_jwt_token):
    """
    Off-nominal test for /api/v3/custom_script/halt
    With a JWT token lacking the correct permissions
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 60,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    time.sleep(10)

    script_run_id = data["scriptRunId"]

    script_status = ""

    while script_status != "PENDING":
        response = auth_client.get(f"/api/v3/custom_script/{script_run_id}")

        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        data = response.json()

        script_status = data["custom_script_status"]
        time.sleep(1)

    assert script_status == "PENDING", (f"Unexpected script completion status {script_status}")

    response = auth_client.post(f"/api/v3/custom_script/{script_run_id}/halt", headers={"Authorization": f"Bearer {no_scope_jwt_token}"})

    assert response.status_code == 401, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(60)
def test_custom_script_halt_expired(auth_client: TestClient, expired_jwt_token):
    """
    Off-nominal test for /api/v3/custom_script/halt
    With an expired JWT Token
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 60,
                         'script_result': 'PASS'}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    time.sleep(10)

    script_run_id = data["scriptRunId"]

    script_status = ""

    while script_status != "PENDING":
        response = auth_client.get(f"/api/v3/custom_script/{script_run_id}")

        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        data = response.json()

        script_status = data["custom_script_status"]
        time.sleep(1)

    assert script_status == "PENDING", (f"Unexpected script completion status {script_status}")

    response = auth_client.post(f"/api/v3/custom_script/{script_run_id}/halt", headers={"Authorization": f"Bearer {expired_jwt_token}"})

    assert response.status_code == 403, (
        f"Unexpected status {response.status_code}: {response.text}"
    )


@pytest.mark.timeout(45)
def test_custom_script_files_unauthorized(auth_client: TestClient, no_scope_jwt_token):
    """
    Off-nominal test for /api/v3/custom_script/files
    With a JWT token that lacks permission
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS',
                         "output_random_data": 1000000}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    script_run_id = data["scriptRunId"]

    script_status = ""

    while script_status != "PASS":
        response = auth_client.get(f"/api/v3/custom_script/{script_run_id}")

        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        data = response.json()

        script_status = data["custom_script_status"]
        time.sleep(1)

    assert script_status == "PASS", (f"Unexpected script completion status {script_status}")

    files = auth_client.get(f"/api/v3/custom_script/{script_run_id}/files", headers={"Authorization": f"Bearer {no_scope_jwt_token}"} )

    assert files.status_code == 401, f"Unexpected status {files.status_code}: {files.text}"


@pytest.mark.timeout(45)
def test_custom_script_files_expired(auth_client: TestClient, expired_jwt_token):
    """
    Off-nominal test for /api/v3/custom_script/files
    With an expired JWT Token
    """
    script_path = Path(__file__).parent / "custom_script_for_tests" / "custom_script_for_tests.py"
    assert script_path.is_file(), f"Script not found: {script_path}"

    inputs = {'inputs': {'duration': 30,
                         'script_result': 'PASS',
                         "output_random_data": 1000000}}

    payload = {
        "scriptName": "custom_script_for_tests",
        "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
        "scriptHash": _sha256(script_path),
        "inputs": inputs,    # No inputs needed for this script.
        "outputs": {"custom_script_status": "PENDING"}
    }

    response = auth_client.post("/api/v3/custom_script/start", json=payload)

    assert response.status_code == 200, (
        f"Unexpected status {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "scriptRunId" in data, "Response JSON missing 'scriptRunId'"

    script_run_id = data["scriptRunId"]

    script_status = ""

    while script_status != "PASS":
        response = auth_client.get(f"/api/v3/custom_script/{script_run_id}")

        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        data = response.json()

        script_status = data["custom_script_status"]
        time.sleep(1)

    assert script_status == "PASS", (f"Unexpected script completion status {script_status}")

    files = auth_client.get(f"/api/v3/custom_script/{script_run_id}/files", headers={"Authorization": f"Bearer {expired_jwt_token}"})

    assert files.status_code == 403, f"Unexpected status {files.status_code}: {files.text}"

