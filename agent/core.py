"""Core runner for the DDNS agent."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ElementTree

import requests

from agent.database import LogDB, UpdateRecord
from shared_lib.schema import AgentConfig
from shared_lib.security import CryptoManager
from shared_lib.url_validation import parse_host_allowlist, validate_url


def _strip_xml_tag(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _parse_namecheap_fields(body: str) -> dict[str, str]:
    if not body or "<" not in body:
        return {}
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return {}
    fields: dict[str, str] = {}
    for elem in root.iter():
        tag = _strip_xml_tag(elem.tag)
        text = (elem.text or "").strip()
        if tag == "ErrCount" and text:
            fields["ErrCount"] = text
        elif tag == "IsSuccess" and text:
            fields["IsSuccess"] = text
        elif tag.startswith("Err") and tag[3:].isdigit() and text:
            fields[tag] = text
        elif tag == "Error" and text and "Err1" not in fields:
            fields["Err1"] = text
        if "IsSuccess" in elem.attrib and "IsSuccess" not in fields:
            fields["IsSuccess"] = elem.attrib["IsSuccess"]
        if "ErrCount" in elem.attrib and "ErrCount" not in fields:
            fields["ErrCount"] = elem.attrib["ErrCount"]
    return fields


def _is_namecheap_error(fields: dict[str, str]) -> bool:
    err_count = fields.get("ErrCount")
    if err_count:
        try:
            if int(err_count) > 0:
                return True
        except ValueError:
            pass
    is_success = fields.get("IsSuccess")
    if is_success and is_success.strip().lower() in {"false", "0", "no"}:
        return True
    return False


def _format_namecheap_message(
    body: str,
    response_code: Optional[int],
    fields: dict[str, str],
) -> str:
    detail_parts: list[str] = []
    if response_code is not None:
        detail_parts.append(f"HTTP {response_code}")
    if fields:
        ordered_fields: list[str] = []
        for key in ("ErrCount", "IsSuccess", "Err1"):
            if key in fields:
                ordered_fields.append(f"{key}={fields[key]}")
        for key, value in fields.items():
            if key in {"ErrCount", "IsSuccess", "Err1"}:
                continue
            ordered_fields.append(f"{key}={value}")
        detail_parts.extend(ordered_fields)
    base = body.strip()
    if detail_parts:
        detail = " | ".join(detail_parts)
        if base:
            return f"{base} ({detail})"
        return detail
    return base


class DDNSRunner:
    """Runs update cycles for DDNS targets."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        db_path: str | Path | None = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        workdir = os.environ.get("DDNS_WORKDIR", ".")
        resolved_config_path = config_path or os.environ.get("AGENT_CONFIG_PATH")
        if resolved_config_path is None:
            # Keep agent defaults in sync with webapp ConfigCompiler.
            resolved_config_path = str(
                Path(workdir) / ".ddns" / "config.enc.json"
            )
        default_db_path = str(Path(workdir) / ".ddns" / "agent.db")
        resolved_db_path = db_path or os.environ.get(
            "AGENT_DB_PATH",
            default_db_path,
        )
        self._config_path = Path(resolved_config_path)
        self._db = LogDB(str(resolved_db_path))
        self._session = session or requests.Session()
        self._config: Optional[AgentConfig] = None
        self._config_mtime: Optional[float] = None
        self._crypto = CryptoManager(self._get_master_key())
        self._check_ip_allowlist = parse_host_allowlist(
            os.environ.get("AGENT_CHECK_IP_HOST_ALLOWLIST")
        )
        self._update_url_allowlist = parse_host_allowlist(
            os.environ.get("AGENT_UPDATE_URL_HOST_ALLOWLIST")
        )

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
        check_ip_url = str(config.check_ip_url)
        try:
            validate_url(check_ip_url, allowed_hosts=self._check_ip_allowlist)
        except ValueError as exc:
            logging.warning("Check IP URL rejected: %s", exc)
            return None
        try:
            response = self._session.get(check_ip_url, timeout=10)
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
        current_ip: Optional[str]
        if config.manual_ip_enabled:
            if config.manual_ip_address:
                current_ip = config.manual_ip_address
                logging.info("Manual override IP in effect: %s", current_ip)
            else:
                logging.warning(
                    "Manual override enabled but no IP configured; "
                    "falling back to public IP lookup."
                )
                current_ip = self._fetch_public_ip(config)
        else:
            current_ip = self._fetch_public_ip(config)
        cached_ip = self._db.get_cache("last_ip")
        skip_unchanged_ip = current_ip and cached_ip == current_ip
        if skip_unchanged_ip:
            logging.info(
                "Public IP unchanged; checking for targets that still need updates."
            )

        if current_ip:
            self._db.set_cache("last_ip", current_ip)

        for target in config.targets:
            if skip_unchanged_ip and current_ip:
                target_cache_key = f"last_ip:{target.id}"
                target_last_ip = self._db.get_cache(target_cache_key)
                if target_last_ip == current_ip:
                    logging.info(
                        "Skipping %s; already updated for current IP.",
                        target.hostname,
                    )
                    continue
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
                try:
                    validate_url(
                        update_url,
                        allowed_hosts=self._update_url_allowlist,
                    )
                except ValueError as exc:
                    message = f"Update URL rejected: {exc}"
                    self._db.log_update(
                        UpdateRecord(
                            target_id=target.id,
                            status="error",
                            message=message,
                            response_code=None,
                            ip_address=current_ip,
                        )
                    )
                    logging.warning(
                        "Skipping %s due to invalid update URL: %s",
                        target.hostname,
                        exc,
                    )
                    continue
                response = self._session.get(update_url, timeout=20)
                response_code = response.status_code
                parsed_fields = _parse_namecheap_fields(response.text)
                status = (
                    "error"
                    if response_code >= 400 or _is_namecheap_error(parsed_fields)
                    else "success"
                )
                message = _format_namecheap_message(
                    response.text,
                    response_code,
                    parsed_fields,
                )
                self._db.log_update(
                    UpdateRecord(
                        target_id=target.id,
                        status=status,
                        message=message,
                        response_code=response_code,
                        ip_address=current_ip,
                    )
                )
                if status == "success" and current_ip:
                    self._db.set_cache(f"last_ip:{target.id}", current_ip)
                if status == "success":
                    logging.info("Updated %s: %s", target.hostname, message)
                else:
                    logging.warning("Update failed for %s: %s", target.hostname, message)
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
