"""Core runner for the DDNS agent."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import requests

from agent.database import LogDB, UpdateRecord
from shared_lib.schema import AgentConfig
from shared_lib.security import CryptoManager


class DDNSRunner:
    """Runs update cycles for DDNS targets."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        db_path: str | Path | None = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        resolved_config_path = config_path or os.environ.get("AGENT_CONFIG_PATH")
        if resolved_config_path is None:
            # Keep agent defaults in sync with webapp ConfigCompiler.
            workdir = os.environ.get("DDNS_WORKDIR", ".")
            resolved_config_path = str(
                Path(workdir) / ".ddns" / "config.enc.json"
            )
        resolved_db_path = db_path or os.environ.get(
            "AGENT_DB_PATH",
            "agent.db",
        )
        self._config_path = Path(resolved_config_path)
        self._db = LogDB(str(resolved_db_path))
        self._session = session or requests.Session()
        self._config: Optional[AgentConfig] = None
        self._config_mtime: Optional[float] = None
        self._crypto = CryptoManager(self._get_master_key())

    def _get_master_key(self) -> str:
        key = os.environ.get("AGENT_MASTER_KEY")
        if not key:
            raise RuntimeError("AGENT_MASTER_KEY is required in the environment")
        return key

    def load_config(self) -> AgentConfig:
        try:
            raw_payload = self._config_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Agent config file not found at {self._config_path!s}. "
                "Set AGENT_CONFIG_PATH or publish configuration from the web UI."
            ) from exc
        self._config_mtime = self._config_path.stat().st_mtime

        if not raw_payload.strip():
            logging.warning(
                "Agent config file %s is empty; waiting for configuration publish.",
                self._config_path,
            )
            check_ip_url = os.environ.get("AGENT_CHECK_IP_URL", "https://api.ipify.org")
            self._config = AgentConfig(check_ip_url=check_ip_url, targets=[])
            return self._config

        try:
            data = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Agent config file {self._config_path!s} is not valid JSON. "
                "Re-publish configuration from the web UI or fix the file contents."
            ) from exc
        if hasattr(AgentConfig, "model_validate"):
            config = AgentConfig.model_validate(data)
        else:
            config = AgentConfig.parse_obj(data)
        self._config = config
        return config

    def load_config_if_changed(self) -> bool:
        try:
            current_mtime = self._config_path.stat().st_mtime
        except FileNotFoundError:
            if self._config_mtime is not None:
                logging.warning(
                    "Agent config file %s is missing; keeping existing config.",
                    self._config_path,
                )
                self._config_mtime = None
            return False

        if self._config_mtime is None or current_mtime != self._config_mtime:
            self.load_config()
            return True
        return False

    def _get_config(self) -> AgentConfig:
        if self._config is None:
            return self.load_config()
        return self._config

    def _fetch_public_ip(self, config: AgentConfig) -> Optional[str]:
        try:
            response = self._session.get(str(config.check_ip_url), timeout=10)
            response.raise_for_status()
            return response.text.strip()
        except requests.RequestException as exc:
            logging.warning("Failed to fetch public IP: %s", exc)
            return None

    def _build_update_url(
        self,
        target_url: str,
        token: str,
        hostname: str,
        target_id: str,
        ip_address: Optional[str],
    ) -> str:
        format_values = {
            "token": token,
            "hostname": hostname,
            "id": target_id,
            "ip": ip_address or "",
        }
        try:
            return target_url.format(**format_values)
        except KeyError:
            return target_url

    def run_once(self) -> None:
        config = self._get_config()
        if not config.targets:
            logging.info("No DDNS targets configured; skipping update cycle.")
            return
        current_ip = self._fetch_public_ip(config)
        cached_ip = self._db.get_cache("last_ip")
        if current_ip and cached_ip == current_ip:
            logging.info("Public IP unchanged; skipping update cycle.")
            return

        if current_ip:
            self._db.set_cache("last_ip", current_ip)

        for target in config.targets:
            token: Optional[str] = None
            try:
                token = self._crypto.decrypt_str(target.encrypted_token)
                update_url = self._build_update_url(
                    str(target.update_url),
                    token,
                    target.hostname,
                    target.id,
                    current_ip,
                )
                response = self._session.get(update_url, timeout=20)
                response.raise_for_status()
                message = response.text.strip()
                self._db.log_update(
                    UpdateRecord(
                        target_id=target.id,
                        status="success",
                        message=message,
                        response_code=response.status_code,
                        ip_address=current_ip,
                    )
                )
                logging.info("Updated %s: %s", target.hostname, message)
            except requests.RequestException as exc:
                self._db.log_update(
                    UpdateRecord(
                        target_id=target.id,
                        status="error",
                        message=str(exc),
                        response_code=getattr(exc.response, "status_code", None),
                        ip_address=current_ip,
                    )
                )
                logging.warning("Update failed for %s: %s", target.hostname, exc)
            except Exception as exc:  # noqa: BLE001 - log and continue other targets
                self._db.log_update(
                    UpdateRecord(
                        target_id=target.id,
                        status="error",
                        message=str(exc),
                        response_code=None,
                        ip_address=current_ip,
                    )
                )
                logging.exception("Unexpected error updating %s", target.hostname)
            finally:
                if token is not None:
                    token = None

    def get_sleep_seconds(self) -> int:
        config = self._get_config()
        if not config.targets:
            return 60
        return max(30, min(target.interval for target in config.targets))

    def close(self) -> None:
        self._db.close()
