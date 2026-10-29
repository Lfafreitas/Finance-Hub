"""Anotações e fontes de leitura do Jornal

Tabelas novas `notes` e `reading_sources`. Nenhum dado existente é alterado.

Revision ID: b3e8c2d4f6a1
Revises: a7d3f9c1e5b2
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b3e8c2d4f6a1"
down_revision: str | Sequence[str] | None = "a7d3f9c1e5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common() -> list:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
    ]


def _stamps() -> list:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "notes",
        *_common(),
        sa.Column("title", sa.String(120)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text()),
        sa.Column("source_title", sa.String(200)),
        sa.Column("source_url", sa.String(500)),
        sa.Column("tickers", sa.String(220), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("share_with_claude", sa.Boolean(), nullable=False),
        *_stamps(),
    )
    op.create_index("ix_notes_user_id", "notes", ["user_id"])
    op.create_table(
        "reading_sources",
        *_common(),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("focus", sa.String(300)),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_stamps(),
    )
    op.create_index("ix_reading_sources_user_id", "reading_sources", ["user_id"])


def downgrade() -> None:
    op.drop_table("reading_sources")
    op.drop_table("notes")
