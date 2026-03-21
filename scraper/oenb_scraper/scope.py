from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CrawlScope:
    primary_hosts: set[str]
    secondary_host_suffixes: set[str] = field(default_factory=set)

    def classify_host(self, host: str) -> str:
        host = (host or "").lower()
        if host in self.primary_hosts:
            return "primary"
        if any(host == suffix or host.endswith(f".{suffix}") for suffix in self.secondary_host_suffixes):
            return "secondary"
        return "out_of_scope"
