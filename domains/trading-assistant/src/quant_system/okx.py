from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from .config import OkxCredentials, OkxSettings, okx_inst_id


class OkxApiError(RuntimeError):
    pass


def okx_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def encode_body(payload: Optional[dict[str, Any]]) -> str:
    if not payload:
        return ""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def okx_number(value: float | str) -> str:
    if isinstance(value, str):
        return value
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def sign_message(secret: str, timestamp: str, method: str, request_path: str, body: str = "") -> str:
    prehash = f"{timestamp}{method.upper()}{request_path}{body}"
    digest = hmac.new(secret.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


class OkxRestClient:
    def __init__(self, settings: OkxSettings, credentials: Optional[OkxCredentials] = None):
        self.settings = settings
        self.credentials = credentials or settings.credentials()

    def _headers(self, method: str, request_path: str, body: str, auth: bool) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "curl/8.7.1",
            "Accept": "application/json",
        }
        if self.settings.demo_trading:
            headers["x-simulated-trading"] = "1"
        if auth:
            if not self.credentials.present:
                raise OkxApiError("OKX credentials are required for authenticated endpoints")
            timestamp = okx_timestamp()
            headers.update(
                {
                    "OK-ACCESS-KEY": self.credentials.api_key,
                    "OK-ACCESS-SIGN": sign_message(
                        self.credentials.api_secret, timestamp, method, request_path, body
                    ),
                    "OK-ACCESS-TIMESTAMP": timestamp,
                    "OK-ACCESS-PASSPHRASE": self.credentials.passphrase,
                }
            )
        return headers

    def request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        payload: Optional[dict[str, Any]] = None,
        auth: bool = False,
    ) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        request_path = f"{path}{query}"
        body = encode_body(payload)
        headers = self._headers(method, request_path, body, auth)
        req = Request(
            f"{self.settings.base_url}{request_path}",
            data=body.encode("utf-8") if body else None,
            headers=headers,
            method=method.upper(),
        )
        try:
            proxy_url = self.settings.effective_proxy_url
            if proxy_url:
                opener = build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url}))
                response_cm = opener.open(req, timeout=self.settings.timeout_seconds)
            else:
                response_cm = urlopen(req, timeout=self.settings.timeout_seconds)
            with response_cm as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OkxApiError(f"OKX HTTP {exc.code}: {detail}") from exc
        data = json.loads(raw)
        if data.get("code") not in (None, "0", 0):
            detail = json.dumps(data.get("data", []), ensure_ascii=False, default=str)
            raise OkxApiError(f"OKX API error {data.get('code')}: {data.get('msg')} data={detail}")
        return data

    def get_candles(self, symbol: str, instrument_type: str, bar: str = "1H", limit: int = 300) -> list[list[str]]:
        return self.request(
            "GET",
            "/api/v5/market/candles",
            params={"instId": okx_inst_id(symbol, instrument_type), "bar": bar, "limit": str(limit)},
        ).get("data", [])

    def get_history_candles(
        self,
        symbol: str,
        instrument_type: str,
        bar: str = "1H",
        after: Optional[str] = None,
        before: Optional[str] = None,
        limit: int = 100,
    ) -> list[list[str]]:
        params: dict[str, Any] = {
            "instId": okx_inst_id(symbol, instrument_type),
            "bar": bar,
            "limit": str(limit),
        }
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        return self.request("GET", "/api/v5/market/history-candles", params=params).get("data", [])

    def get_instruments(self, instrument_type: str) -> list[dict[str, Any]]:
        inst_type = "SPOT" if instrument_type == "spot" else "SWAP"
        return self.request("GET", "/api/v5/public/instruments", params={"instType": inst_type}).get("data", [])

    def get_funding_rate(self, symbol: str) -> dict[str, Any]:
        data = self.request(
            "GET", "/api/v5/public/funding-rate", params={"instId": okx_inst_id(symbol, "swap")}
        ).get("data", [])
        return data[0] if data else {}

    def get_funding_rate_history(
        self,
        symbol: str,
        after: Optional[str] = None,
        before: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"instId": okx_inst_id(symbol, "swap"), "limit": str(limit)}
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        return self.request("GET", "/api/v5/public/funding-rate-history", params=params).get("data", [])

    def get_balance(self) -> dict[str, Any]:
        return self.request("GET", "/api/v5/account/balance", auth=True)

    def get_account_config(self) -> dict[str, Any]:
        return self.request("GET", "/api/v5/account/config", auth=True)

    def get_account_instruments(self, instrument_type: str) -> list[dict[str, Any]]:
        inst_type = "SPOT" if instrument_type == "spot" else "SWAP"
        return self.request(
            "GET", "/api/v5/account/instruments", params={"instType": inst_type}, auth=True
        ).get("data", [])

    def get_ticker(self, symbol: str, instrument_type: str) -> dict[str, Any]:
        data = self.request(
            "GET", "/api/v5/market/ticker", params={"instId": okx_inst_id(symbol, instrument_type)}
        ).get("data", [])
        return data[0] if data else {}

    def get_tickers(self, instrument_type: str) -> list[dict[str, Any]]:
        inst_type = "SPOT" if instrument_type == "spot" else "SWAP"
        return self.request("GET", "/api/v5/market/tickers", params={"instType": inst_type}).get("data", [])

    def get_open_interest(self, symbol: str, instrument_type: str = "swap") -> list[dict[str, Any]]:
        inst_type = "SWAP" if instrument_type == "swap" else "SPOT"
        return self.request(
            "GET",
            "/api/v5/public/open-interest",
            params={"instType": inst_type, "instId": okx_inst_id(symbol, instrument_type)},
        ).get("data", [])

    def get_orderbook(self, symbol: str, instrument_type: str, depth: int = 50) -> dict[str, Any]:
        data = self.request(
            "GET",
            "/api/v5/market/books",
            params={"instId": okx_inst_id(symbol, instrument_type), "sz": str(depth)},
        ).get("data", [])
        return data[0] if data else {}

    def get_recent_trades(self, symbol: str, instrument_type: str, limit: int = 100) -> list[dict[str, Any]]:
        return self.request(
            "GET",
            "/api/v5/market/trades",
            params={"instId": okx_inst_id(symbol, instrument_type), "limit": str(limit)},
        ).get("data", [])

    def get_mark_price(self, symbol: str, instrument_type: str = "swap") -> dict[str, Any]:
        inst_type = "SWAP" if instrument_type == "swap" else "SPOT"
        data = self.request(
            "GET",
            "/api/v5/public/mark-price",
            params={"instType": inst_type, "instId": okx_inst_id(symbol, instrument_type)},
        ).get("data", [])
        return data[0] if data else {}

    def get_index_ticker(self, symbol: str) -> dict[str, Any]:
        base, quote = symbol.split("/", 1)
        data = self.request(
            "GET",
            "/api/v5/market/index-tickers",
            params={"instId": f"{base}-{quote}"},
        ).get("data", [])
        return data[0] if data else {}

    def get_contract_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        base, _quote = symbol.split("/", 1)
        return self.request(
            "GET",
            "/api/v5/rubik/stat/contracts/long-short-account-ratio",
            params={"ccy": base, "period": period, "limit": str(limit)},
        ).get("data", [])

    def get_liquidation_orders(
        self,
        symbol: str,
        instrument_type: str = "swap",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        inst_type = "SWAP" if instrument_type == "swap" else "SPOT"
        return self.request(
            "GET",
            "/api/v5/public/liquidation-orders",
            params={"instType": inst_type, "instId": okx_inst_id(symbol, instrument_type), "limit": str(limit)},
        ).get("data", [])

    def get_positions(self, symbol: Optional[str] = None, instrument_type: Optional[str] = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if instrument_type:
            params["instType"] = "SPOT" if instrument_type == "spot" else "SWAP"
        if symbol and instrument_type:
            params["instId"] = okx_inst_id(symbol, instrument_type)
        return self.request("GET", "/api/v5/account/positions", params=params, auth=True).get("data", [])

    def place_order(
        self,
        symbol: str,
        instrument_type: str,
        side: str,
        quantity: float | str,
        order_type: str = "market",
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        reduce_only: bool = False,
        margin_mode: str = "cross",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "instId": okx_inst_id(symbol, instrument_type),
            "tdMode": "cash" if instrument_type == "spot" else margin_mode,
            "side": side,
            "ordType": "market" if order_type == "market" else "limit",
            "sz": okx_number(quantity),
        }
        if price is not None:
            payload["px"] = str(price)
        if client_order_id:
            payload["clOrdId"] = client_order_id
        if reduce_only:
            payload["reduceOnly"] = "true"
        return self.request("POST", "/api/v5/trade/order", payload=payload, auth=True)

    def set_leverage(
        self,
        symbol: str,
        instrument_type: str,
        leverage: float,
        margin_mode: str = "cross",
    ) -> dict[str, Any]:
        if instrument_type == "spot":
            raise OkxApiError("spot instruments do not use leverage")
        payload = {
            "instId": okx_inst_id(symbol, instrument_type),
            "lever": str(leverage),
            "mgnMode": margin_mode,
        }
        return self.request("POST", "/api/v5/account/set-leverage", payload=payload, auth=True)

    def cancel_order(
        self,
        symbol: str,
        instrument_type: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"instId": okx_inst_id(symbol, instrument_type)}
        if order_id:
            payload["ordId"] = order_id
        if client_order_id:
            payload["clOrdId"] = client_order_id
        return self.request("POST", "/api/v5/trade/cancel-order", payload=payload, auth=True)

    def cancel_all_after(self, timeout_seconds: int) -> dict[str, Any]:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be >= 0")
        return self.request(
            "POST",
            "/api/v5/trade/cancel-all-after",
            payload={"timeOut": str(timeout_seconds)},
            auth=True,
        )


class OkxWebSocketClient:
    def __init__(self, settings: OkxSettings):
        self.settings = settings

    @property
    def public_url(self) -> str:
        host = "wspap.okx.com" if self.settings.demo_trading else "ws.okx.com"
        return f"wss://{host}:8443/ws/v5/public"

    @property
    def private_url(self) -> str:
        host = "wspap.okx.com" if self.settings.demo_trading else "ws.okx.com"
        return f"wss://{host}:8443/ws/v5/private"

    def subscribe_message(self, channels: list[dict[str, str]]) -> str:
        return json.dumps({"op": "subscribe", "args": channels}, separators=(",", ":"))

    def ticker_channels(self, symbols: list[str], instrument_type: str) -> list[dict[str, str]]:
        return [{"channel": "tickers", "instId": okx_inst_id(symbol, instrument_type)} for symbol in symbols]

    def candle_channels(self, symbols: list[str], instrument_type: str, bar: str) -> list[dict[str, str]]:
        channel = f"candle{bar}"
        return [{"channel": channel, "instId": okx_inst_id(symbol, instrument_type)} for symbol in symbols]

    @staticmethod
    def login_message(credentials: OkxCredentials) -> str:
        timestamp = str(int(time.time()))
        sign = sign_message(credentials.api_secret, timestamp, "GET", "/users/self/verify", "")
        return json.dumps(
            {
                "op": "login",
                "args": [
                    {
                        "apiKey": credentials.api_key,
                        "passphrase": credentials.passphrase,
                        "timestamp": timestamp,
                        "sign": sign,
                    }
                ],
            },
            separators=(",", ":"),
        )
