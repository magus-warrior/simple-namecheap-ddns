"""Database models for the web application."""

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Secret(db.Model):
    __tablename__ = "secrets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    encrypted_value = db.Column(db.Text, nullable=False)

    targets = db.relationship(
        "Target",
        back_populates="secret",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Secret id={self.id} name={self.name!r}>"


class Target(db.Model):
    __tablename__ = "targets"

    id = db.Column(db.Integer, primary_key=True)
    host = db.Column(db.String(255), nullable=False)
    domain = db.Column(db.String(255), nullable=False)
    secret_id = db.Column(db.Integer, db.ForeignKey("secrets.id"), nullable=False)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)

    secret = db.relationship("Secret", back_populates="targets")

    def __repr__(self) -> str:
        return f"<Target id={self.id} host={self.host!r} domain={self.domain!r}>"
