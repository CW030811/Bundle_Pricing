from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import AppConfig


def config_fingerprint(config: AppConfig) -> str:
    payload = config.model_dump(mode="json")
    return _hash_json(payload)


def code_fingerprint(root: Path | None = None) -> str:
    base = root or Path(__file__).resolve().parents[2]
    source_root = base / "src" / "quant_system"
    digest = hashlib.sha256()
    for path in sorted(source_root.glob("*.py")):
        if path.name == "__pycache__":
            continue
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def reproducibility_payload(
    config: AppConfig,
    *,
    artifact_type: str,
    artifact_name: str,
    data_version: str = "v1",
    factor_version: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "artifact_name": artifact_name,
        "data_version": data_version,
        "factor_version": factor_version,
        "code_fingerprint": code_fingerprint(),
        "config_fingerprint": config_fingerprint(config),
        "parameters": parameters or {},
    }


def _hash_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
