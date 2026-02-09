from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ConcurrencyLimits:
    """Hierarchy: task profile > provider > default."""

    task_profiles: dict[str, int] = field(default_factory=dict)
    providers: dict[str, int] = field(default_factory=dict)
    default: int | None = None


@dataclass(slots=True, frozen=True)
class ConcurrencyToken:
    bucket: str


class ConcurrencyManager:
    def __init__(self, limits: ConcurrencyLimits | None = None) -> None:
        self._limits = limits or ConcurrencyLimits()
        self._inflight_by_bucket: dict[str, int] = {}

    def try_acquire(self, profile: str, provider: str | None = None) -> ConcurrencyToken | None:
        bucket, limit = self._resolve_bucket(profile=profile, provider=provider)
        if limit is None:
            return ConcurrencyToken(bucket="unbounded")

        inflight = self._inflight_by_bucket.get(bucket, 0)
        if inflight >= limit:
            return None

        self._inflight_by_bucket[bucket] = inflight + 1
        return ConcurrencyToken(bucket=bucket)

    def release(self, token: ConcurrencyToken) -> None:
        if token.bucket == "unbounded":
            return

        inflight = self._inflight_by_bucket.get(token.bucket, 0)
        if inflight <= 1:
            self._inflight_by_bucket.pop(token.bucket, None)
            return
        self._inflight_by_bucket[token.bucket] = inflight - 1

    def limit_for(self, profile: str, provider: str | None = None) -> int | None:
        _, limit = self._resolve_bucket(profile=profile, provider=provider)
        return limit

    def inflight_for(self, profile: str, provider: str | None = None) -> int:
        bucket, limit = self._resolve_bucket(profile=profile, provider=provider)
        if limit is None:
            return 0
        return self._inflight_by_bucket.get(bucket, 0)

    def _resolve_bucket(self, profile: str, provider: str | None) -> tuple[str, int | None]:
        profile_limit = self._limits.task_profiles.get(profile)
        if profile_limit is not None:
            return f"profile:{profile}", _normalize_limit(profile_limit)

        if provider is not None:
            provider_limit = self._limits.providers.get(provider)
            if provider_limit is not None:
                return f"provider:{provider}", _normalize_limit(provider_limit)

        return "default", _normalize_limit(self._limits.default)


def _normalize_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    if limit <= 0:
        return None
    return limit
