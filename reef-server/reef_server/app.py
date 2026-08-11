import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from reef_server.constants import ARCHIVE_FILENAME, DEFAULT_BUNDLE_DIR, LOG_FORMAT, LOGGER_NAME
from reef_server.errors import ReefServiceError
from reef_server.service import ReefService


def _configure_logging(min_level: int = logging.INFO) -> None:
    """
    Attach Reef's handler to the `reef_server` package logger, leaving the root logger untouched.

    Every module under `reef_server` propagates up to this logger and stops there, so our lines keep
    their format whatever the host process did to root, and libraries logging at INFO do not
    leak into our output. The handler is added once, so re-importing this module is harmless.
    """
    reef_logger = logging.getLogger(LOGGER_NAME)
    reef_logger.setLevel(min_level)
    reef_logger.propagate = False

    if not reef_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        reef_logger.addHandler(handler)


app = FastAPI(title="Reef - Airflow DAG Bundle Server")

_configure_logging()
logger = logging.getLogger(__name__)

bundle_dir = Path(os.getenv("DAGS_DIR", DEFAULT_BUNDLE_DIR))

reef_server_version = os.getenv("REEF_SERVER_VERSION")
dags_version = os.getenv("DAGS_VERSION")

logger.info("Reef is starting up")
logger.info(f"Serving bundles out of: {bundle_dir}")
logger.info(f"Bundle version: {dags_version}")
logger.info(f"Reef version: {reef_server_version}")

_service = ReefService(
    bundle_dir=bundle_dir,
    bundle_version=dags_version,
    server_version=reef_server_version,
    logger=logger,
)


@app.exception_handler(ReefServiceError)
async def handle_service_error(_: Request, exc: ReefServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


@app.get("/api/v1/health")
def liveness():
    return _service.check_liveness()


@app.get("/api/v1/information")
def service_info():
    return _service.describe_service()


@app.get("/api/v1/dags/metadata")
def bundle_metadata():
    return _service.describe_bundle()


@app.get("/api/v1/dags/download")
def download_bundle():
    archive_path = _service.resolve_bundle_archive()
    return FileResponse(archive_path, media_type="application/gzip", filename=ARCHIVE_FILENAME)


@app.get("/api/v1/ready")
def readiness_probe():
    checks = _service.evaluate_readiness()
    if not checks["healthy"]:
        return JSONResponse(status_code=503, content=checks)
    return checks
