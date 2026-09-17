# Ingenium Venue Agent (VenueServer) Deep Wiki

## Overview

The **Ingenium Venue Agent** (also referred to as **VenueServer**) is a Python [FastAPI](https://fastapi.tiangolo.com/) service that exposes a small, secure REST API for executing, monitoring, and halting custom test scripts on a host that is physically or logically connected to a test venue. It is part of the Ingenium ground-data-system (GDS) toolchain and is typically deployed behind an NGINX reverse proxy.

In a typical flow a client supplies the relative path to a custom script, the SHA-256 hash of that script, and a set of inputs. VenueServer validates the path and hash, spawns the script in an isolated process, tracks the process in Redis, and exposes endpoints for status, log-tail, halting, and file download.

## Repository Layout

```text
.
├── main.py                     # FastAPI app, routes, middleware, startup
├── utils.py                    # JWT loading, decoding, and scope validation
├── openapi.yaml                # Canonical OpenAPI 3.1.0 spec
├── log_config.yaml             # Logging config (uses pyaml-env)
├── nginx.conf.template         # NGINX reverse-proxy template
├── requirements.txt            # Runtime Python dependencies
├── setup_venueserver.sh        # Creates venv and generates nginx.conf
├── start_venueserver.sh        # Starts the FastAPI/uvicorn server
├── start_nginx.sh              # Starts/stops/reloads NGINX
├── start_redis.sh              # (stub) Redis startup helper
├── config/
│   └── venueserver_dev_envs.sh # Example environment variables
├── core/
│   ├── __init__.py
│   ├── schema.py               # Pydantic request/response models
│   ├── venue_core.py           # Custom-script orchestration
│   ├── worker_process.py       # Standalone ProcessPoolExecutor worker
│   └── core_utils.py           # Environment helper and TimeoutError
└── tests/
    ├── conftest.py             # pytest fixtures (JWT, FakeRedis, logging)
    ├── test_health.py          # Health endpoint tests
    ├── test_custom_script.py   # Custom-script lifecycle tests
    ├── _jwt_env.py             # Generates ephemeral RSA keys for tests
    └── custom_script_for_tests/
        └── custom_script_for_tests.py  # Sample script for the test suite
```

## Technology Stack

| Component | Purpose |
|---|---|
| Python 3.10–3.14 | Runtime (CI matrix in `.github/workflows/tests.yml`) |
| FastAPI 0.141.1 | REST API framework |
| Uvicorn 0.52.1 | ASGI server |
| Pydantic 2.13.4 | Request/response validation |
| Redis 8.1.0 | Runtime state persistence (`localhost:6379`, db `0`) |
| PyJWT 2.13.0 + cryptography 50.0.0 | RS256 JWT validation |
| pyaml-env 1.2.2 | YAML log config with environment substitution |
| tailer 0.4.1 | Tail log files for status response |
| psutil 7.2.2 | Process/zombie detection |
| NGINX | SSL termination and multi-instance reverse proxy |

## Architecture & Data Flow

### 1. Request Ingress

`main.py` constructs a FastAPI application and mounts an `APIRouter` under the prefix `/api/v3`. All requests pass through two middlewares:

1. **`check_jwt`**: Validates the `Authorization: Bearer <jwt>` header. The JWT is decoded with the RSA public key `exec_venue_public_pem.pem` using `RS256`. The middleware skips authentication for `/docs`, `/openapi.json`, `/openapi.yaml`, and any path ending in `/health`. It then checks the `scopes` claim for an accepted scope.
2. **`log_request`**: Logs the HTTP method, path, elapsed time, status code, username, and a truncated copy of JSON responses for observability.

### 2. Custom Script Lifecycle

The business logic lives in `core/venue_core.py`:

#### Start

```
POST /api/v3/custom_script/start
```

1. The request body is validated against `ScriptStartBodyModel` in `core/schema.py`. `scriptPath` must be relative and must not contain `..` or `~`.
2. `start_custom_script()` joins `scriptPath` with the `CUSTOM_SCRIPT_BASE_DIR` environment variable.
3. It checks that the file exists and verifies the client-provided SHA-256 hash against the file.
4. It creates a `/tmp/cs/<timestamp>-<uuid>/` working directory.
5. It writes the inputs to `input.json` and an initial `output.json`.
6. It launches the script as a new process group (`preexec_fn=os.setsid`) with `PYTHONUNBUFFERED=YES`, redirecting stdout and stderr to `script.log`.
7. Run metadata (PID, output path, log path, log URL, working directory) is serialized as JSON and stored in Redis under the generated `scriptRunId`.

#### Status

```
GET /api/v3/custom_script/{script_run_id}
```

`get_custom_script_status()` fetches the Redis record, checks process liveness with `os.kill(pid, 0)` and `psutil`, reads `output.json` (with retry logic for partial writes), and appends the last 25 lines of `script.log` using `tailer`. If a process has exited but the status is still `PENDING`, the status is rewritten to `ERROR`.

#### Halt

```
POST /api/v3/custom_script/{script_run_id}/halt
```

`halt_custom_script()` sends `SIGTERM` to the entire process group and removes the Redis record.

#### File Download

```
GET /api/v3/custom_script/{script_run_id}/files
```

`get_custom_script_files()` packages `input.json`, `output.json`, and `script.log` into a `tar.gz` and returns it as `application/gzip`.

### 3. Models

`core/schema.py` defines the Pydantic data classes used by the API:

- `HealthStatusEnum` / `HealthStatus` — `OK`, `ERROR`, `UNKNOWN`.
- `ScriptStartBodyModel` — `scriptName`, `scriptPath`, `scriptHash`, `inputs`, `outputs`.
- `ScriptRunInfo` — `scriptRunId`.
- `ScriptStatusResp` — `custom_script_status`, `custom_script_outputs`, `logfile_path`, `logfile_lines`, `logfile_url`.
- `CustomScriptOutputs` / `ScriptEntriesModel` / `CustomScriptStatus` / `VerificationStatus`.
- `ErrorResponse` — generic error payload.

## REST API Reference

| Method | Path | Auth? | Description |
|---|---|---|---|
| `GET` | `/api/v3/health` | No | Returns `HealthStatus` |
| `POST` | `/api/v3/custom_script/start` | Yes | Start a custom script |
| `GET` | `/api/v3/custom_script/{script_run_id}` | Yes | Get status and outputs |
| `POST` | `/api/v3/custom_script/{script_run_id}/halt` | Yes | Halt a running script |
| `GET` | `/api/v3/custom_script/{script_run_id}/files` | Yes | Download `tar.gz` of run files |

OpenAPI documentation is available at `/docs`, `/openapi.json`, and `/openapi.yaml`. The canonical spec is also committed in `openapi.yaml`.

### Example: Start a Script

```bash
curl -X POST https://host:9443/api/v3/custom_script/start \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "scriptName": "test_cs",
    "scriptPath": "custom_script_for_tests/custom_script_for_tests.py",
    "scriptHash": "<sha256-hex>",
    "inputs": {"inputs": {"duration": 30, "script_result": "PASS"}},
    "outputs": {"custom_script_status": "PENDING"}
  }'
```

A successful response:

```json
{
  "scriptRunId": "<uuid>"
}
```

### Example: Check Status

```bash
curl -H "Authorization: Bearer <jwt>" \
  https://host:9443/api/v3/custom_script/{script_run_id}
```

The response includes the current `custom_script_status`, the parsed `custom_script_outputs`, the last 25 log lines, and a `logfile_url` for downloading files.

### Example: Download Files

```bash
curl -H "Authorization: Bearer <jwt>" \
  https://host:9443/api/v3/custom_script/{script_run_id}/files \
  -o {script_run_id}.tar.gz
```

## Authentication & Authorization

Authentication is JWT-based using RS256.

- On import, `utils.py` loads the RSA public key from `exec_venue_public_pem.pem` in the repo root and computes a CRC32 checksum for log identification.
- Every protected request must provide `Authorization: Bearer <token>`.
- The token payload must contain a `scopes` array. Each scope can be a string or an object such as `{"scope": "execute:testbed"}`.
- One of the following scopes is required:
  - `execute:wsts`
  - `execute:sit`
  - `execute:testbed`
  - `execute:other`

If the token is missing, malformed, or has an invalid signature, the service returns `401`. If the token is valid but lacks an accepted scope, it returns `403`.

## Custom Script Contract

A custom script is any executable file located under `CUSTOM_SCRIPT_BASE_DIR`. VenueServer invokes it as:

```bash
/path/to/script /tmp/cs/<timestamp>-<uuid>/input.json /tmp/cs/<timestamp>-<uuid>/output.json
```

The script is expected to:

1. Read `input.json`.
2. Optionally write intermediate output to `output.json`.
3. On completion, set `custom_script_status` in `output.json` to one of: `PENDING`, `ERROR`, `PASS`, `FAIL`.
4. Write any logs to stdout/stderr, which are captured in `script.log`.

The `tests/custom_script_for_tests/custom_script_for_tests.py` file is a reference implementation that supports `duration`, `script_result`, `exception_time`, `heavy_writes`, and `output_random_data` inputs.

## Environment Variables & Configuration

| Variable | Purpose | Example |
|---|---|---|
| `ING_VENUE_DIR` | Root directory of the VenueServer code | `/opt/local/ingenium/venueserver/<release>` |
| `ING_LOG_DIR` | Directory for `ing_vs.log` | `/home/$USER/ingenium/<hostname>/logs` |
| `CUSTOM_SCRIPT_BASE_DIR` | Root directory where custom scripts are stored | `/project/ing/scripts` |

`setup_venueserver.sh` and `start_venueserver.sh` source an environment file (for example `config/venueserver_dev_envs.sh`) and then run the service. `log_config.yaml` uses `pyaml-env` to inject `${ING_LOG_DIR}` at load time:

```yaml
handlers:
  rotating_file:
    class: logging.handlers.RotatingFileHandler
    filename: !ENV '${ING_LOG_DIR}/ing_vs.log'
    maxBytes: 50000000
    backupCount: 20
```

## Deployment & Operations

### Development Setup

1. Ensure Redis is running:
   ```bash
   ps -ealf | grep redis-server
   ```
2. Configure `config/venueserver_dev_envs.sh` for the local host.
3. Create the virtual environment and generate `nginx.conf`:
   ```bash
   ./setup_venueserver.sh -f config/venueserver_dev_envs.sh
   ```
4. Start VenueServer:
   ```bash
   ./start_venueserver.sh -p 19443 -f config/venueserver_dev_envs.sh
   ```
5. Check the unproxied health endpoint:
   ```bash
   curl http://localhost:19443/api/v3/health
   ```

### Production Deployment

The typical production layout is:

- One NGINX process with three `server` blocks on ports `9443`, `9444`, and `9445`.
- One or more VenueServer processes on ports `19443`, `19444`, `19445`.
- One shared Redis instance on `localhost:6379`.
- Each VenueServer runs under a different user account so that logs and temp directories can be isolated.
- `setup_venueserver.sh` substitutes `$HOME`, `$HOSTNAME`, `$SHORT_HOSTNAME`, and `$ING_VENUE_DIR` into `nginx.conf.template` to produce `nginx.conf`.

### Starting and Stopping NGINX

```bash
./start_nginx.sh start
./start_nginx.sh stop
./start_nginx.sh reload
```

The NGINX configuration also sets HSTS, TLS 1.2, and a fixed cipher suite. SSL certificates are read from `config/.secret/.server.crt` and `.server.key` under `ING_VENUE_DIR`.

## Testing

The test suite uses `pytest` and is executed in GitHub Actions across Python 3.10–3.14.

```bash
pip install -r requirements.txt
pip install -r tests/requirements.txt
python -m pytest tests/
```

Key fixtures in `tests/conftest.py`:

- `jwt_token` — signs a JWT with an ephemeral RSA private key.
- `expired_jwt_token` / `no_scope_jwt_token` — negative-case tokens.
- `fake_redis` — patches `redis.Redis` with `fakeredis` for the test session.
- `auth_client` — `TestClient` pre-configured with the bearer token.
- `per_test_logging` — writes a per-test log to a temp directory.

`tests/_jwt_env.py` generates the ephemeral RSA key pair and writes the public key to `exec_venue_public_pem.pem` in the repo root so `utils.py` can load it. It also sets `JWT_PRIVATE_KEY` and `CUSTOM_SCRIPT_BASE_DIR` for the test run.

Important test cases include:

- Health endpoint success and method checks (`test_health.py`).
- Successful start/status/halt/file download of a custom script.
- Off-nominal start cases: absolute path, `..` traversal, `~` in path, missing file, mismatched hash.

## Security Considerations

- **Path traversal protection**: `scriptPath` must be relative and cannot contain `..` or `~`; it is resolved under `CUSTOM_SCRIPT_BASE_DIR`.
- **Integrity**: Each script is verified with a client-provided SHA-256 hash before execution.
- **Process isolation**: Custom scripts run in their own process group (`os.setsid`), and halting terminates the entire process group.
- **Authentication**: RS256 JWT with a public key on disk; scope-based authorization.
- **Temp directory permissions**: The working directory base `/tmp/cs` is created with broad read/write/execute permissions (`stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU`) so multiple application users can share it.

## Logging

Runtime logs are written to:

- `ing_vs.log` in `${ING_LOG_DIR}` (rotating, 50 MB, 20 backups).
- Standard output via `console` handler.

`main.py` logs the environment, public-key CRC32, request ID, method, path, and (for JSON responses) a truncated copy of the response body. NGINX maintains separate access and error logs for each SSL port.

## Notes & Known Behavior

- `core/worker_process.py` is a standalone `ProcessPoolExecutor` wrapper and is not currently wired into the FastAPI routes. It exists as a reusable worker utility.
- `venue_core.py` uses `localhost:6379` and DB `0` directly for Redis. In a test environment this is patched to `fakeredis`.
- If a custom script exits without updating `custom_script_status` from `PENDING`, VenueServer automatically rewrites the status to `ERROR` on the next status call.
- The `/api/v3/custom_script/{script_run_id}/halt` endpoint returns `204 No Content` on success.
