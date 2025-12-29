"""Flask application entrypoint for the DDNS web UI."""

from __future__ import annotations

import os

from flask import Flask

from webapp import bp, db


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, static_folder=None)
    db_path = os.environ.get("WEBAPP_DB_PATH", "webapp.db")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        FLASK_MASTER_KEY=os.environ.get("FLASK_MASTER_KEY"),
        AGENT_DB_PATH=os.environ.get("AGENT_DB_PATH", "agent.db"),
    )

    db.init_app(app)
    app.register_blueprint(bp)

    with app.app_context():
        db.create_all()

    return app


app = create_app()
