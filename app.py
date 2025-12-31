"""Flask application entrypoint for the DDNS web UI."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask
from sqlalchemy import text

from webapp import bp, db


def _ensure_interval_minutes_column() -> None:
    """Add interval_minutes to targets table if it's missing."""
    with db.engine.begin() as connection:
        result = connection.execute(text("PRAGMA table_info(targets)")).fetchall()
        if not result:
            return
        columns = {row[1] for row in result}
        if "interval_minutes" in columns:
            return
        connection.execute(
            text(
                "ALTER TABLE targets "
                "ADD COLUMN interval_minutes INTEGER NOT NULL DEFAULT 5"
            )
        )
def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, static_folder=None)
    db_path = os.environ.get("WEBAPP_DB_PATH", "webapp.db")
    workdir = os.environ.get("DDNS_WORKDIR", ".")
    default_agent_db_path = str(
        Path(workdir) / ".ddns" / "agent.db"
    )
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        FLASK_MASTER_KEY=os.environ.get("FLASK_MASTER_KEY"),
        AGENT_DB_PATH=os.environ.get("AGENT_DB_PATH", default_agent_db_path),
    )

    db.init_app(app)
    app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
        _ensure_interval_minutes_column()

    return app


app = create_app()
