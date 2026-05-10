"""
models.py — SQLAlchemy ORM table definitions.

Two tables:
  - Url   : stores the short_code → long_url mapping and metadata
  - Click : append-only event log for every redirect (enables analytics)

Schema is intentionally minimal — only what the platform needs to operate and
expose useful metrics. No business-logic columns.
"""

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Url(Base):
    """One row per shortened URL."""

    __tablename__ = "urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    short_code: Mapped[str] = mapped_column(
        String(16),
        unique=True,
        nullable=False,
        index=True,  # every redirect does a PK-equivalent lookup here
    )

    long_url: Mapped[str] = mapped_column(String(2048), nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationship — used by stats route to count clicks without a raw query
    clicks: Mapped[list["Click"]] = relationship(
        "Click",
        back_populates="url",
        lazy="dynamic",  # don't load all clicks eagerly; use .count() instead
    )


class Click(Base):
    """
    Append-only event row written on every GET /{code} redirect.

    Keeping clicks as rows (rather than a counter column on Url) means:
    - No lost-update races under concurrent traffic
    - Analytics queries (clicks per hour, per day) become trivial SELECTs
    - The DB load from click writes is observable via db_connections_active
    """

    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    url_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("urls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    clicked_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    url: Mapped["Url"] = relationship("Url", back_populates="clicks")
