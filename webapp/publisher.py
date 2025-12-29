"""Compile and publish agent configuration from the webapp models."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

from shared_lib.schema import AgentConfig, AgentTarget
from shared_lib.security import CryptoManager
from webapp.models import Target


class ConfigCompiler:
    """Builds and publishes encrypted agent configurations."""

    def __init__(
        self,
        flask_key: str,
        agent_key: str,
        check_ip_url: str,
        update_url_template: str = (
            "https://dynamicdns.park-your-domain.com/update"
            "?host={hostname}&domain={domain}&password={token}&ip={ip}"
        ),
        config_path: str | Path = "/etc/ddns-agent/config.enc.json",
        service_name: str = "ddns-agent",
        default_interval: int = 300,
    ) -> None:
        self._flask_crypto = CryptoManager(flask_key)
        self._agent_crypto = CryptoManager(agent_key)
        self._check_ip_url = check_ip_url
        self._update_url_template = update_url_template
        self._config_path = Path(config_path)
        self._service_name = service_name
        self._default_interval = default_interval

    def _split_hosts(self, hostnames: str) -> list[str]:
        hosts = [host.strip() for host in hostnames.split(",")]
        return [host for host in hosts if host]

    def _build_target(self, target: Target, hostname: str) -> AgentTarget:
        secret_value = self._flask_crypto.decrypt_str(target.secret.encrypted_value)
        encrypted_token = self._agent_crypto.encrypt_str(secret_value)
        update_url = self._update_url_template.format(
            hostname=hostname,
            domain=target.domain,
            token="{token}",
            ip="{ip}",
            id=target.id,
        )
        return AgentTarget(
            id=str(target.id),
            hostname=hostname,
            update_url=update_url,
            encrypted_token=encrypted_token,
            interval=self._default_interval,
        )

    def compile(self, targets: Iterable[Target]) -> AgentConfig:
        active_targets = [t for t in targets if t.is_enabled]
        expanded_targets: list[AgentTarget] = []
        for target in active_targets:
            for hostname in self._split_hosts(target.host):
                expanded_targets.append(self._build_target(target, hostname))
        return AgentConfig(
            check_ip_url=self._check_ip_url,
            targets=expanded_targets,
        )

    def publish(self, targets: Iterable[Target]) -> AgentConfig:
        config = self.compile(targets)
        payload = json.dumps(
            config.model_dump() if hasattr(config, "model_dump") else config.dict(),
            indent=2,
        )
        self._write_atomic(payload)
        self._reload_service()
        return config

    def _write_atomic(self, payload: str) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self._config_path.parent,
            delete=False,
        ) as handle:
            handle.write(payload)
            temp_name = handle.name
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, self._config_path)

    def _reload_service(self) -> None:
        subprocess.run([\"systemctl\", \"reload\", self._service_name], check=True)
