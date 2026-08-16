"""Small persistence protocol used by services and source clients."""

from __future__ import annotations

from typing import Any, Protocol


class CacheRepository(Protocol):
    def get_external_cache(self, source: str, cache_key: str) -> dict[str, Any] | None: ...

    def put_external_cache(
        self,
        source: str,
        cache_key: str,
        payload: dict[str, Any],
        fetched_at: str,
        expires_at: str,
        source_url: str,
    ) -> None: ...

    def record_external_failure(
        self,
        source: str,
        cache_key: str,
        failed_at: str,
        error: str,
        circuit_open_until: str | None,
    ) -> None: ...
