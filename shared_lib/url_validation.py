"""URL validation helpers for remote service requests."""

from __future__ import annotations

import ipaddress
from typing import Iterable
from urllib.parse import urlparse


def parse_host_allowlist(raw_value: str | None) -> set[str]:
    if not raw_value:
        return set()
    return {
        host.strip().lower()
        for host in raw_value.split(",")
        if host.strip()
    }


def validate_url(value: str, *, allowed_hosts: Iterable[str] | None = None) -> None:
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme != "https":
        raise ValueError("URL must use https://")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname")

    host = parsed.hostname.lower()
    if host == "localhost":
        raise ValueError("URL hostname cannot be localhost")

    try:
        ip_address = ipaddress.ip_address(host)
    except ValueError:
        ip_address = None

    if ip_address and (
        ip_address.is_private
        or ip_address.is_loopback
        or ip_address.is_link_local
        or ip_address.is_reserved
        or ip_address.is_multicast
        or ip_address.is_unspecified
    ):
        raise ValueError("URL hostname cannot be a loopback or private IP")

    if allowed_hosts:
        allowed_set = {host_name.lower() for host_name in allowed_hosts}
        if host not in allowed_set:
            raise ValueError(f"URL host {host} is not in the allowlist")
