"""HTTP routes for managing DDNS targets and secrets."""

from __future__ import annotations

import sqlite3
from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request

from shared_lib.security import CryptoManager
from webapp.models import Secret, Target, db

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


def _get_crypto() -> CryptoManager:
    key = current_app.config.get("FLASK_MASTER_KEY")
    if not key:
        raise RuntimeError("FLASK_MASTER_KEY is required for encrypting secrets")
    return CryptoManager(key)


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
    }


@bp.get("/secrets")
def list_secrets() -> Any:
    secrets = Secret.query.order_by(Secret.name).all()
    return jsonify([_secret_to_dict(secret) for secret in secrets])


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
    return jsonify(_secret_to_dict(secret)), 201


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
    return jsonify(_secret_to_dict(secret))


@bp.delete("/secrets/<int:secret_id>")
def delete_secret(secret_id: int) -> Any:
    secret = Secret.query.get_or_404(secret_id)
    db.session.delete(secret)
    db.session.commit()
    return jsonify({"status": "deleted"})


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
    if not host or not domain or not secret_id:
        return jsonify({"error": "host, domain, and secret_id are required"}), 400

    target = Target(
        host=host,
        domain=domain,
        secret_id=secret_id,
        is_enabled=bool(is_enabled),
    )
    db.session.add(target)
    db.session.commit()
    return jsonify(_target_to_dict(target)), 201


@bp.get("/targets/<int:target_id>")
def get_target(target_id: int) -> Any:
    target = Target.query.get_or_404(target_id)
    return jsonify(_target_to_dict(target))


@bp.put("/targets/<int:target_id>")
def update_target(target_id: int) -> Any:
    target = Target.query.get_or_404(target_id)
    payload = request.get_json(silent=True) or {}
    if "host" in payload:
        target.host = payload.get("host")
    if "domain" in payload:
        target.domain = payload.get("domain")
    if "secret_id" in payload:
        target.secret_id = payload.get("secret_id")
    if "is_enabled" in payload:
        target.is_enabled = bool(payload.get("is_enabled"))
    db.session.commit()
    return jsonify(_target_to_dict(target))


@bp.delete("/targets/<int:target_id>")
def delete_target(target_id: int) -> Any:
    target = Target.query.get_or_404(target_id)
    db.session.delete(target)
    db.session.commit()
    return jsonify({"status": "deleted"})


@bp.get("/dashboard")
def dashboard() -> Any:
    db_path = current_app.config.get("AGENT_DB_PATH", "agent.db")
    limit = int(request.args.get("limit", 25))
    rows: list[dict[str, Any]] = []
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
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
