"""Centralized configuration and logging setup."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import structlog
from dotenv import load_dotenv
import uptrace
from pydantic_settings import BaseSettings
from pydantic import Field
import logging
import sys
import yaml
from structlog.dev import ConsoleRenderer
from structlog.stdlib import ProcessorFormatter
from typing import Any, MutableMapping, Mapping, Callable, Sequence

from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# ---- OTLP Log Exporter ----
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor


# --------------------------------------------------------------------------- #
# 1. Load .env early                                                           #
# --------------------------------------------------------------------------- #

ENV_PATH = Path(os.getenv("ENV_PATH", ".env"))
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)  # silent overwrite = True by default


# --------------------------------------------------------------------------- #
# 2. Settings dataclass                                                       #
# --------------------------------------------------------------------------- #

class Settings(BaseSettings):
    # Opentelemetry / Uptrace
    uptrace_dsn: str = Field("", env="UPTRACE_DSN")
    oltp_exporter_endpoint: str = Field("", env="OLTP_EXPORTER_ENDPOINT")
    deploy_env: str = Field("development", env="DEPLOY_ENV")

    # App-specific
    config_path: Path = Field("/app/config.yaml", env="CONFIG_PATH")
    db_path: Path = Field("/data/calendar_sync.db", env="DB_PATH")
    log_level: str = Field("INFO", env="LOG_LEVEL")

    # Logging
    json_log: bool = Field(False, env="JSON_LOG")

    class Config:
        frozen = True          # make it hashable / safe
        env_file = None        # already loaded manually via dotenv


settings = Settings()  # triggers validation

# Convert textual log level to numeric constant once
LOG_LEVEL_INT = getattr(logging, settings.log_level.upper(), logging.INFO)

# --------------------------------------------------------------------------- #
# Common log processors                                                       #
# --------------------------------------------------------------------------- #

pre_chain: Sequence[
    Callable[[Any, str, MutableMapping[str, Any]], Mapping[str, Any] | str | bytes | bytearray | tuple[Any, ...]]
] = [
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.add_log_level,
]

def _jsonify_record(
    _logger: structlog.types.WrappedLogger,
    _method: str,
    event_dict: MutableMapping[str, Any],
) -> Mapping[str, Any]:
    """Convert stdlib LogRecord into a JSON‑serializable subset."""
    record = event_dict.get("_record")
    if record is not None and not isinstance(record, dict):
        event_dict["_record"] = {
            "name": record.name,
            "file": record.pathname,
            "line": record.lineno,
            "func": record.funcName,
        }
    event_dict.pop("_from_structlog", None)
    return event_dict

def configure_logging() -> None:
    """Initialize structlog + stdlib logging (JSON or colorful console)."""
    if settings.json_log:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = ConsoleRenderer(colors=True, force_colors=True)

    processor_formatter = ProcessorFormatter(
        foreign_pre_chain=pre_chain,
        processors=[*pre_chain, _jsonify_record, renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(processor_formatter)

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(LOG_LEVEL_INT)

    if settings.oltp_exporter_endpoint:
        resource = Resource.create({SERVICE_NAME: "calendar-sync"})
        trace.set_tracer_provider(TracerProvider(resource=resource))
        # OTLP Exporter
        otlp_exporter = OTLPSpanExporter(endpoint=settings.oltp_exporter_endpoint, insecure="true")
        span_processor = BatchSpanProcessor(otlp_exporter)
        trace.get_tracer_provider().add_span_processor(span_processor)

        # ---- OTLP Log Exporter ----
        logger_provider = LoggerProvider(resource=resource)
        set_logger_provider(logger_provider)
        log_exporter = OTLPLogExporter(endpoint=settings.oltp_exporter_endpoint, insecure=True)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        log_handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
        logging.getLogger().addHandler(log_handler)

    # OpenTelemetry via Uptrace
    elif settings.uptrace_dsn:
        uptrace.configure_opentelemetry(
            dsn=settings.uptrace_dsn,
            service_name="calendar-sync",
            service_version="0.1.0",
            deployment_environment=settings.deploy_env,
        )

    structlog.configure(
        processors=[*pre_chain, _jsonify_record, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(root.level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

# Run logging configuration at import time
configure_logging()

logger = structlog.get_logger(__name__)

# ----------------------------------------------------------------------- #
# 5. External config.yaml (required)                                    #
# ----------------------------------------------------------------------- #
def _load_yaml_config(path: Path) -> Dict[str, Any]:
    """Load YAML configuration from *path* into a dictionary."""
    if not path.exists():
        raise FileNotFoundError(f"config.yaml not found at {path}")
    try:
        with path.open("r") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("config.yaml must contain a top-level mapping")
    return data

yaml_config: Dict[str, Any] = _load_yaml_config(settings.config_path)
logger.info("YAML config loaded", path=str(settings.config_path), keys=list(yaml_config.keys()))

__all__ = [
    "settings",
    "Settings",
    "configure_logging",
]
