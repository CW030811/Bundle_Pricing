from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import AppConfig
from .okx import OkxApiError, OkxRestClient


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: dict[str, Any]


def summarize_exception(exc: Exception) -> dict[str, str]:
    return {"error_type": type(exc).__name__, "error": str(exc)[:500]}


def results_to_payload(results: list[CheckResult]) -> list[dict[str, Any]]:
    return [{"name": result.name, "ok": result.ok, "detail": result.detail} for result in results]


def readiness_summary(results: list[CheckResult]) -> dict[str, Any]:
    by_name = {result.name: result for result in results}
    public_ok = by_name.get("public_time", CheckResult("public_time", False, {})).ok
    demo_ok = by_name.get("demo_private_auth", CheckResult("demo_private_auth", False, {})).ok
    production_ok = by_name.get(
        "production_private_auth_readonly", CheckResult("production_private_auth_readonly", False, {})
    ).ok
    blockers: list[str] = []
    if not public_ok:
        blockers.append("OKX public API is not reachable")
    if not demo_ok:
        blockers.append("Demo Trading API credentials are missing or invalid")
    return {
        "ready_for_demo_trading": public_ok and demo_ok,
        "public_api_ok": public_ok,
        "demo_private_auth_ok": demo_ok,
        "production_private_auth_readonly_ok": production_ok,
        "blockers": blockers,
        "checks": results_to_payload(results),
    }


def diagnose_okx(config: AppConfig) -> list[CheckResult]:
    results: list[CheckResult] = []

    public_client = OkxRestClient(config.okx)
    try:
        data = public_client.request("GET", "/api/v5/public/time")
        results.append(CheckResult("public_time", True, {"code": data.get("code")}))
    except Exception as exc:
        results.append(CheckResult("public_time", False, summarize_exception(exc)))

    demo_cfg = config.model_copy(deep=True)
    demo_cfg.okx.demo_trading = True
    demo_creds = demo_cfg.okx.credentials()
    if not demo_creds.present:
        results.append(
            CheckResult(
                "demo_private_auth",
                False,
                {
                    "error_type": "MissingCredentials",
                    "error": "set OKX_DEMO_API_KEY, OKX_DEMO_API_SECRET, and OKX_DEMO_PASSPHRASE",
                    "credential_environment": demo_creds.environment,
                },
            )
        )
    else:
        try:
            data = OkxRestClient(demo_cfg.okx).get_account_config()
            item = (data.get("data") or [{}])[0]
            results.append(
                CheckResult(
                    "demo_private_auth",
                    True,
                    {
                        "acctLv": item.get("acctLv"),
                        "posMode": item.get("posMode"),
                        "uid_present": bool(item.get("uid")),
                        "credential_environment": demo_creds.environment,
                    },
                )
            )
        except Exception as exc:
            results.append(CheckResult("demo_private_auth", False, {**summarize_exception(exc), "credential_environment": demo_creds.environment}))

    prod_cfg = config.model_copy(deep=True)
    prod_cfg.okx.demo_trading = False
    prod_creds = prod_cfg.okx.credentials()
    if not prod_creds.present:
        results.append(
            CheckResult(
                "production_private_auth_readonly",
                False,
                {
                    "error_type": "MissingCredentials",
                    "error": "set OKX_API_KEY, OKX_API_SECRET, and OKX_PASSPHRASE",
                    "credential_environment": prod_creds.environment,
                },
            )
        )
        return results
    try:
        data = OkxRestClient(prod_cfg.okx).get_account_config()
        item = (data.get("data") or [{}])[0]
        results.append(
            CheckResult(
                "production_private_auth_readonly",
                True,
                {
                    "acctLv": item.get("acctLv"),
                    "posMode": item.get("posMode"),
                    "uid_present": bool(item.get("uid")),
                    "credential_environment": prod_creds.environment,
                },
            )
        )
    except Exception as exc:
        results.append(CheckResult("production_private_auth_readonly", False, {**summarize_exception(exc), "credential_environment": prod_creds.environment}))

    return results
