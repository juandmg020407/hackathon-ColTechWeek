"""Uniform resilience policy for free external JSON sources."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..repositories.contracts import CacheRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class SourcePolicy:
    timeout_seconds: float = 5.0
    max_retries: int = 2
    backoff_seconds: float = 0.15
    jitter_seconds: float = 0.10
    ttl_seconds: int = 10_800
    circuit_failure_threshold: int = 3
    circuit_cooldown_seconds: int = 300


@dataclass(frozen=True)
class SourceResult:
    source: str
    source_url: str
    payload: dict[str, Any] | None
    fetched_at: str | None
    degraded: bool
    stale: bool
    failed: bool
    warning: str | None = None

    def evidence(self) -> dict[str, Any]:
        return {
            "name": self.source,
            "url": self.source_url,
            "fetched_at": self.fetched_at,
            "degraded": self.degraded,
            "stale": self.stale,
            "failed": self.failed,
        }


class ResilientJSONSource:
    """HTTP JSON source with durable cache, retry and a simple circuit breaker."""

    def __init__(
        self,
        *,
        name: str,
        url: str,
        repository: CacheRepository,
        policy: SourcePolicy,
        enabled: bool,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.name = name
        self.url = url
        self.repository = repository
        self.policy = policy
        self.enabled = enabled
        self.transport = transport

    @staticmethod
    def cache_key(params: dict[str, Any]) -> str:
        encoded = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode()).hexdigest()

    async def fetch(
        self,
        params: dict[str, Any],
        *,
        offline_payload: dict[str, Any] | None = None,
        offline_fetched_at: str | None = None,
    ) -> SourceResult:
        key = self.cache_key(params)
        cached = self.repository.get_external_cache(self.name, key)
        now = _utc_now()
        if cached and cached.get("payload") and (
            expires_at := _parse_time(cached.get("expires_at"))
        ) and expires_at > now:
            return SourceResult(
                source=self.name,
                source_url=cached.get("source_url") or self.url,
                payload=cached["payload"],
                fetched_at=cached.get("fetched_at"),
                degraded=False,
                stale=False,
                failed=False,
            )

        if not self.enabled:
            return self._fallback(
                cached,
                offline_payload,
                offline_fetched_at,
                "el acceso a Internet está desactivado; se usa un fixture versionado sin conexión",
            )

        circuit_until = _parse_time(cached.get("circuit_open_until")) if cached else None
        if circuit_until and circuit_until > now:
            return self._fallback(
                cached,
                offline_payload,
                offline_fetched_at,
                f"el cortacircuitos sigue abierto hasta {circuit_until.isoformat()}",
            )

        last_error = "fallo no identificado de la fuente"
        seeded_random = random.Random(f"{self.name}:{key}")
        for attempt in range(self.policy.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.policy.timeout_seconds,
                    transport=self.transport,
                ) as client:
                    response = await client.get(self.url, params=params)
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ValueError("la respuesta de la fuente debe ser un objeto JSON")
                fetched_at = _utc_now()
                expires_at = fetched_at + timedelta(seconds=self.policy.ttl_seconds)
                self.repository.put_external_cache(
                    self.name,
                    key,
                    payload,
                    fetched_at.isoformat().replace("+00:00", "Z"),
                    expires_at.isoformat().replace("+00:00", "Z"),
                    str(response.url),
                )
                return SourceResult(
                    source=self.name,
                    source_url=str(response.url),
                    payload=payload,
                    fetched_at=fetched_at.isoformat().replace("+00:00", "Z"),
                    degraded=False,
                    stale=False,
                    failed=False,
                )
            except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
                last_error = f"{type(error).__name__}: {error}"
                if attempt < self.policy.max_retries:
                    delay = (
                        self.policy.backoff_seconds * (2 ** attempt)
                        + seeded_random.uniform(0, self.policy.jitter_seconds)
                    )
                    await asyncio.sleep(delay)

        failure_count = int(cached.get("failure_count") or 0) + 1 if cached else 1
        circuit_open_until = None
        if failure_count >= self.policy.circuit_failure_threshold:
            circuit_open_until = (
                now + timedelta(seconds=self.policy.circuit_cooldown_seconds)
            ).isoformat().replace("+00:00", "Z")
        self.repository.record_external_failure(
            self.name,
            key,
            now.isoformat().replace("+00:00", "Z"),
            last_error,
            circuit_open_until,
        )
        return self._fallback(cached, offline_payload, offline_fetched_at, last_error)

    def _fallback(
        self,
        cached: dict[str, Any] | None,
        offline_payload: dict[str, Any] | None,
        offline_fetched_at: str | None,
        reason: str,
    ) -> SourceResult:
        payload = cached.get("payload") if cached else None
        fetched_at = cached.get("fetched_at") if cached else None
        source_url = cached.get("source_url") if cached else self.url
        if payload is None:
            payload = offline_payload
            fetched_at = offline_fetched_at
        return SourceResult(
            source=self.name,
            source_url=source_url or self.url,
            payload=payload,
            fetched_at=fetched_at,
            degraded=True,
            stale=True,
            failed=True,
            warning=f"{self.name}: {reason}. El dato no se presenta como actual.",
        )
