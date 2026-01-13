"""HTTP routes for managing DDNS targets and secrets."""

from __future__ import annotations

import ipaddress
import os
import sqlite3
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ElementTree

from flask import Blueprint, abort, current_app, jsonify, render_template, request
import requests

from agent.database import LogDB, UpdateRecord
from shared_lib.security import CryptoManager
from shared_lib.url_validation import parse_host_allowlist, validate_url
from webapp.publisher import ConfigCompiler
from webapp.models import AppSettings, Secret, Target, db

bp = Blueprint(
    "webapp",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


@bp.get("/")
def index() -> str:
    return render_template("index.html")


def _get_flask_key() -> str:
    key = current_app.config.get("FLASK_MASTER_KEY")
    if not key:
        raise RuntimeError("FLASK_MASTER_KEY is required for encrypting secrets")
    return key


def _get_crypto() -> CryptoManager:
    return CryptoManager(_get_flask_key())


def _get_agent_key() -> str:
    key = os.environ.get("AGENT_MASTER_KEY")
    if key:
        return key

    workdir = os.environ.get("DDNS_WORKDIR")
    if not workdir:
        workdir = str(Path(__file__).resolve().parents[1])
    env_path = Path(workdir) / ".ddns" / "agent.env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line or line.strip().startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "AGENT_MASTER_KEY":
                return value.strip()

    raise RuntimeError("AGENT_MASTER_KEY is required to publish agent config")


def _get_app_settings() -> AppSettings:
    settings = AppSettings.query.first()
    if settings is None:
        settings = AppSettings(manual_ip_enabled=False, manual_ip_address=None)
        db.session.add(settings)
        db.session.commit()
    return settings


def _publish_config() -> dict[str, Any] | None:
    try:
        check_ip_url = _get_check_ip_url()
        update_url_template = _get_update_url_template()
    except RuntimeError as exc:
        current_app.logger.warning("Invalid URL configuration: %s", exc)
        return {
            "error": "Invalid URL configuration.",
            "detail": str(exc),
        }
    compiler = ConfigCompiler(
        flask_key=_get_flask_key(),
        agent_key=_get_agent_key(),
        check_ip_url=check_ip_url,
        update_url_template=update_url_template,
    )
    targets = Target.query.order_by(Target.id).all()
    settings = _get_app_settings()
    try:
        compiler.publish(targets, settings)
    except (OSError, RuntimeError) as exc:
        config_path = getattr(compiler, "_config_path", None)
        current_app.logger.exception(
            "Failed to publish config to %s", config_path or "<unknown>"
        )
        hint_parts = [
            "Check file permissions for the config path.",
            "Ensure the agent process is running to pick up changes.",
        ]
        return {
            "error": "Unable to publish agent configuration.",
            "detail": str(exc),
            "config_path": str(config_path) if config_path else None,
            "hint": " ".join(hint_parts),
        }
    return None


def _secret_to_dict(secret: Secret) -> dict[str, Any]:
    return {
        "id": secret.id,
        "name": secret.name,
    }


def _target_to_dict(target: Target) -> dict[str, Any]:
    return {
        "id": target.id,
        "host": target.host,
        "domain": target.domain,
        "secret_id": target.secret_id,
        "is_enabled": target.is_enabled,
        "interval_minutes": target.interval_minutes,
    }


def _settings_to_dict(settings: AppSettings) -> dict[str, Any]:
    return {
        "manual_ip_enabled": settings.manual_ip_enabled,
        "manual_ip_address": settings.manual_ip_address,
    }


def _coerce_interval_minutes(
    payload: dict[str, Any],
    default_minutes: int = 5,
    use_default_if_missing: bool = False,
) -> int | None:
    if "interval_minutes" not in payload:
        return default_minutes if use_default_if_missing else None
    try:
        value = int(payload.get("interval_minutes", default_minutes))
    except (TypeError, ValueError):
        return None
    return value


def _normalize_hostnames(value: str) -> str:
    hosts = [host.strip() for host in value.split(",")]
    normalized: list[str] = []
    seen = set()
    for host in hosts:
        if not host or host in seen:
            continue
        normalized.append(host)
        seen.add(host)
    return ", ".join(normalized)


def _split_hostnames(value: str) -> list[str]:
    return [host.strip() for host in value.split(",") if host.strip()]


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
    response_code: int | None,
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


def _get_check_ip_url() -> str:
    check_ip_url = os.environ.get("AGENT_CHECK_IP_URL", "https://api.ipify.org")
    allowlist = parse_host_allowlist(
        os.environ.get("AGENT_CHECK_IP_HOST_ALLOWLIST")
    )
    try:
        validate_url(check_ip_url, allowed_hosts=allowlist)
    except ValueError as exc:
        raise RuntimeError(f"AGENT_CHECK_IP_URL is invalid: {exc}") from exc
    return check_ip_url


def _get_update_url_template() -> str:
    update_url_template = os.environ.get(
        "AGENT_UPDATE_URL_TEMPLATE",
        (
            "https://dynamicdns.park-your-domain.com/update"
            "?host={hostname}&domain={domain}&password={token}&ip={ip}"
        ),
    )
    allowlist = parse_host_allowlist(
        os.environ.get("AGENT_UPDATE_URL_HOST_ALLOWLIST")
    )
    try:
        validate_url(update_url_template, allowed_hosts=allowlist)
    except ValueError as exc:
        raise RuntimeError(f"AGENT_UPDATE_URL_TEMPLATE is invalid: {exc}") from exc
    return update_url_template


def _fetch_public_ip() -> str | None:
    try:
        check_ip_url = _get_check_ip_url()
    except RuntimeError as exc:
        current_app.logger.warning("Invalid check IP URL: %s", exc)
        return None
    try:
        response = requests.get(check_ip_url, timeout=10)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException:
        current_app.logger.exception("Unable to fetch public IP from %s", check_ip_url)
        return None


def _normalize_manual_ip(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(ipaddress.ip_address(str(value)))


@bp.get("/secrets")
def list_secrets() -> Any:
    secrets = Secret.query.order_by(Secret.name).all()
    return jsonify([_secret_to_dict(secret) for secret in secrets])


@bp.get("/settings")
def get_settings() -> Any:
    settings = _get_app_settings()
    return jsonify(_settings_to_dict(settings))


@bp.put("/settings")
def update_settings() -> Any:
    settings = _get_app_settings()
    payload = request.get_json(silent=True) or {}
    manual_ip_enabled = (
        bool(payload.get("manual_ip_enabled"))
        if "manual_ip_enabled" in payload
        else settings.manual_ip_enabled
    )
    manual_ip_address = settings.manual_ip_address
    if "manual_ip_address" in payload:
        try:
            manual_ip_address = _normalize_manual_ip(
                payload.get("manual_ip_address")
            )
        except ValueError:
            return (
                jsonify(
                    {
                        "error": (
                            "manual_ip_address must be a valid IPv4 or IPv6 address"
                        )
                    }
                ),
                400,
            )
    if manual_ip_enabled and not manual_ip_address:
        return (
            jsonify(
                {
                    "error": (
                        "manual_ip_address is required when manual_ip_enabled is true"
                    )
                }
            ),
            400,
        )

    settings.manual_ip_enabled = manual_ip_enabled
    settings.manual_ip_address = manual_ip_address
    db.session.commit()
    publish_error = _publish_config()
    response_payload = _settings_to_dict(settings)
    if publish_error:
        response_payload["publish_error"] = publish_error
    return jsonify(response_payload)


@bp.post("/secrets")
def create_secret() -> Any:
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    value = payload.get("value")
    if not name or not value:
        return jsonify({"error": "name and value are required"}), 400

    crypto = _get_crypto()
    secret = Secret(name=name, encrypted_value=crypto.encrypt_str(value))
    db.session.add(secret)
    db.session.commit()
    publish_error = _publish_config()
    payload = _secret_to_dict(secret)
    if publish_error:
        payload["publish_error"] = publish_error
    return jsonify(payload), 201


@bp.get("/secrets/<int:secret_id>")
def get_secret(secret_id: int) -> Any:
    secret = Secret.query.get_or_404(secret_id)
    return jsonify(_secret_to_dict(secret))


@bp.put("/secrets/<int:secret_id>")
def update_secret(secret_id: int) -> Any:
    secret = Secret.query.get_or_404(secret_id)
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    value = payload.get("value")
    if name:
        secret.name = name
    if value:
        crypto = _get_crypto()
        secret.encrypted_value = crypto.encrypt_str(value)
    db.session.commit()
    publish_error = _publish_config()
    payload = _secret_to_dict(secret)
    if publish_error:
        payload["publish_error"] = publish_error
    return jsonify(payload)


@bp.delete("/secrets/<int:secret_id>")
def delete_secret(secret_id: int) -> Any:
    secret = Secret.query.get_or_404(secret_id)
    db.session.delete(secret)
    db.session.commit()
    publish_error = _publish_config()
    payload = {"status": "deleted"}
    if publish_error:
        payload["publish_error"] = publish_error
    return jsonify(payload)


@bp.get("/targets")
def list_targets() -> Any:
    targets = Target.query.order_by(Target.id).all()
    return jsonify([_target_to_dict(target) for target in targets])


@bp.post("/targets")
def create_target() -> Any:
    payload = request.get_json(silent=True) or {}
    host = payload.get("host")
    domain = payload.get("domain")
    secret_id = payload.get("secret_id")
    is_enabled = payload.get("is_enabled", True)
    interval_minutes = _coerce_interval_minutes(
        payload,
        default_minutes=5,
        use_default_if_missing=True,
    )
    if not host or not domain or not secret_id:
        return jsonify({"error": "host, domain, and secret_id are required"}), 400
    if not Secret.query.get(secret_id):
        return jsonify({"error": "secret_id does not exist"}), 400
    normalized_host = _normalize_hostnames(host)
    if not normalized_host:
        return jsonify({"error": "host is required"}), 400
    if interval_minutes is None or interval_minutes < 1:
        return jsonify({"error": "interval_minutes must be a positive integer"}), 400

    target = Target(
        host=normalized_host,
        domain=domain,
        secret_id=secret_id,
        is_enabled=bool(is_enabled),
        interval_minutes=interval_minutes,
    )
    db.session.add(target)
    db.session.commit()
    publish_error = _publish_config()
    payload = _target_to_dict(target)
    if publish_error:
        payload["publish_error"] = publish_error
    return jsonify(payload), 201


@bp.get("/targets/<int:target_id>")
def get_target(target_id: int) -> Any:
    target = Target.query.get_or_404(target_id)
    return jsonify(_target_to_dict(target))


@bp.put("/targets/<int:target_id>")
def update_target(target_id: int) -> Any:
    target = Target.query.get_or_404(target_id)
    payload = request.get_json(silent=True) or {}
    if "host" in payload:
        normalized_host = _normalize_hostnames(payload.get("host") or "")
        if not normalized_host:
            return jsonify({"error": "host is required"}), 400
        target.host = normalized_host
    if "domain" in payload:
        domain = payload.get("domain")
        if not domain:
            return jsonify({"error": "domain is required"}), 400
        target.domain = domain
    if "secret_id" in payload:
        secret_id = payload.get("secret_id")
        if not secret_id:
            return jsonify({"error": "secret_id is required"}), 400
        if not Secret.query.get(secret_id):
            return jsonify({"error": "secret_id does not exist"}), 400
        target.secret_id = secret_id
    if "is_enabled" in payload:
        target.is_enabled = bool(payload.get("is_enabled"))
    interval_minutes = _coerce_interval_minutes(payload)
    if "interval_minutes" in payload:
        if interval_minutes is None or interval_minutes < 1:
            return jsonify({"error": "interval_minutes must be a positive integer"}), 400
        target.interval_minutes = interval_minutes
    db.session.commit()
    publish_error = _publish_config()
    payload = _target_to_dict(target)
    if publish_error:
        payload["publish_error"] = publish_error
    return jsonify(payload)


@bp.delete("/targets/<int:target_id>")
def delete_target(target_id: int) -> Any:
    target = Target.query.get_or_404(target_id)
    db.session.delete(target)
    db.session.commit()
    publish_error = _publish_config()
    payload = {"status": "deleted"}
    if publish_error:
        payload["publish_error"] = publish_error
    return jsonify(payload)


@bp.post("/targets/<int:target_id>/force")
def force_target_update(target_id: int) -> Any:
    target = Target.query.get_or_404(target_id)
    try:
        crypto = _get_crypto()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    secret_value = crypto.decrypt_str(target.secret.encrypted_value)
    ip_address = _fetch_public_ip()
    if not ip_address:
        return jsonify({"error": "Unable to fetch public IP"}), 502

    hostnames = _split_hostnames(target.host)
    if not hostnames:
        return jsonify({"error": "Target hostnames are empty"}), 400

    try:
        update_url_template = _get_update_url_template()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    results: list[dict[str, Any]] = []
    log_db = LogDB(current_app.config.get("AGENT_DB_PATH", "agent.db"))
    try:
        for hostname in hostnames:
            update_url = update_url_template.format(
                hostname=hostname,
                domain=target.domain,
                token=secret_value,
                ip=ip_address,
                id=target.id,
            )
            try:
                response = requests.get(update_url, timeout=20)
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
            except requests.RequestException as exc:
                response = getattr(exc, "response", None)
                response_code = getattr(response, "status_code", None)
                parsed_fields = (
                    _parse_namecheap_fields(response.text) if response else {}
                )
                message = str(exc)
                status = "error"
                if parsed_fields or response_code is not None:
                    message = _format_namecheap_message(
                        message if not response else response.text,
                        response_code,
                        parsed_fields,
                    )

            log_db.log_update(
                UpdateRecord(
                    target_id=str(target.id),
                    status=status,
                    message=message,
                    response_code=response_code,
                    ip_address=ip_address,
                )
            )
            results.append(
                {
                    "hostname": hostname,
                    "status": status,
                    "message": message,
                    "parsed_fields": parsed_fields,
                    "response_code": response_code,
                }
            )
    finally:
        log_db.close()

    return jsonify(
        {
            "target_id": target.id,
            "ip_address": ip_address,
            "results": results,
        }
    )


@bp.get("/dashboard")
def dashboard() -> Any:
    db_path = current_app.config.get("AGENT_DB_PATH", "agent.db")
    limit = int(request.args.get("limit", 25))
    rows: list[dict[str, Any]] = []
    if not Path(db_path).is_file():
        resolved_path = Path(db_path).expanduser().resolve()
        current_app.logger.warning(
            "Agent DB not found at %s (resolved: %s)",
            db_path,
            resolved_path,
        )
        return jsonify({"logs": rows})
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        current_app.logger.exception("Unable to open agent DB at %s", db_path)
        return jsonify({"logs": rows})
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.execute(
            """
            SELECT target_id, status, message, response_code, ip_address, created_at
            FROM update_history
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        for row in cursor.fetchall():
            rows.append({
                "target_id": row["target_id"],
                "status": row["status"],
                "message": row["message"],
                "response_code": row["response_code"],
                "ip_address": row["ip_address"],
                "created_at": row["created_at"],
            })
    finally:
        connection.close()
    return jsonify({"logs": rows})
