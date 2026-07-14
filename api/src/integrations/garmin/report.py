from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SyncReport:
    status: str = "success"
    domains: dict[str, dict[str, Any]] = field(default_factory=dict)
    counts: dict[str, int] = field(
        default_factory=lambda: {"created": 0, "updated": 0, "deleted": 0}
    )
    created_ids: list[str] = field(default_factory=list)
    updated_ids: list[str] = field(default_factory=list)
    deleted_ids: list[str] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)

    def add_domain(self, name: str, result: Any) -> None:
        if isinstance(result, dict):
            domain = dict(result)
        else:
            domain = {"result": result}
        self.domains[name] = domain
        for key in ("created", "updated", "deleted"):
            value = domain.get(key)
            if isinstance(value, int):
                self.counts[key] += value
        if domain.get("status") in {"failed", "error"}:
            self.status = "failed"
            self.failures.append({"domain": name, **domain})

    def add_failure(self, domain: str, error: Exception | str) -> None:
        self.status = "failed"
        self.failures.append({"domain": domain, "error": str(error)})
        self.domains[domain] = {"status": "failed", "error": str(error)}

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "domains": self.domains,
            "counts": self.counts,
            "created_ids": self.created_ids,
            "updated_ids": self.updated_ids,
            "deleted_ids": self.deleted_ids,
            "skipped": self.skipped,
            "failures": self.failures,
        }
