"""cf2: categorias, tags e regras de classificação do livro de caixa

Revision ID: b4c9e7d1a3f6
Revises: f1d8b3a6c2e9
Create Date: 2026-10-06

Tabelas novas: cashflow_categories, cashflow_tags, cashflow_rules e as
duas de associação. `cashflow_entries` ganha `category_id` e
`classified_by_rule_id` — ambas classificação, nulas em todo lançamento
existente. Nenhum dado é migrado.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c9e7d1a3f6"
down_revision: str | Sequence[str] | None = "f1d8b3a6c2e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "cashflow_categories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name="ck_cashflow_categories_not_own_parent"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["cashflow_categories.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cashflow_categories_parent_id"), "cashflow_categories", ["parent_id"], unique=False
    )
    op.create_index(
        op.f("ix_cashflow_categories_user_id"), "cashflow_categories", ["user_id"], unique=False
    )
    op.create_index(
        "uq_cashflow_categories_child_name",
        "cashflow_categories",
        ["user_id", "parent_id", "name"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NOT NULL"),
    )
    op.create_index(
        "uq_cashflow_categories_root_name",
        "cashflow_categories",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NULL"),
    )
    op.create_table(
        "cashflow_tags",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tag_group", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tag_group", "name", name="uq_cashflow_tags_group_name"),
    )
    op.create_index(op.f("ix_cashflow_tags_user_id"), "cashflow_tags", ["user_id"], unique=False)
    op.create_table(
        "cashflow_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "match_type",
            sa.Enum("CONTAINS", "EQUALS", "STARTS_WITH", name="cashflow_rule_match_type"),
            nullable=False,
        ),
        sa.Column("pattern", sa.String(length=200), nullable=False),
        sa.Column(
            "direction", sa.Enum("ANY", "IN", "OUT", name="cashflow_rule_direction"), nullable=False
        ),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column(
            "set_nature", postgresql.ENUM(name="cashflow_nature", create_type=False), nullable=False
        ),
        sa.Column("set_category_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "set_nature NOT IN ('TRANSFER', 'UNCLASSIFIED')",
            name="ck_cashflow_rules_sets_a_real_nature",
        ),
        sa.CheckConstraint(
            "length(btrim(pattern)) > 0", name="ck_cashflow_rules_pattern_not_blank"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["set_category_id"],
            ["cashflow_categories.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cashflow_rules_account_id"), "cashflow_rules", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_cashflow_rules_set_category_id"),
        "cashflow_rules",
        ["set_category_id"],
        unique=False,
    )
    op.create_index(op.f("ix_cashflow_rules_user_id"), "cashflow_rules", ["user_id"], unique=False)
    op.create_table(
        "cashflow_rule_tags",
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("tag_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["cashflow_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["cashflow_tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("rule_id", "tag_id"),
    )
    op.create_index(
        op.f("ix_cashflow_rule_tags_tag_id"), "cashflow_rule_tags", ["tag_id"], unique=False
    )
    op.create_table(
        "cashflow_entry_tags",
        sa.Column("entry_id", sa.UUID(), nullable=False),
        sa.Column("tag_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["cashflow_entries.id"],
        ),
        sa.ForeignKeyConstraint(["tag_id"], ["cashflow_tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("entry_id", "tag_id"),
    )
    op.create_index(
        op.f("ix_cashflow_entry_tags_tag_id"), "cashflow_entry_tags", ["tag_id"], unique=False
    )
    op.add_column("cashflow_entries", sa.Column("category_id", sa.UUID(), nullable=True))
    op.add_column("cashflow_entries", sa.Column("classified_by_rule_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_cashflow_entries_category_id"), "cashflow_entries", ["category_id"], unique=False
    )
    op.create_index(
        op.f("ix_cashflow_entries_classified_by_rule_id"),
        "cashflow_entries",
        ["classified_by_rule_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_cashflow_entries_category_id",
        "cashflow_entries",
        "cashflow_categories",
        ["category_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_cashflow_entries_classified_by_rule_id",
        "cashflow_entries",
        "cashflow_rules",
        ["classified_by_rule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_cashflow_entries_transfer_has_no_category",
        "cashflow_entries",
        "nature <> 'TRANSFER' OR category_id IS NULL",
    )

    # Categoria tem no máximo dois níveis: o pai de uma subcategoria não
    # pode ter pai, e uma categoria que já tem filhas não vira filha.
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_cashflow_category_depth()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.parent_id IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM cashflow_categories
                    WHERE id = NEW.parent_id AND parent_id IS NOT NULL
                ) THEN
                    RAISE EXCEPTION
                        'categoria %: a categoria pai já é uma subcategoria (máximo de dois níveis)',
                        NEW.id
                        USING ERRCODE = '23000';
                END IF;
                IF EXISTS (SELECT 1 FROM cashflow_categories WHERE parent_id = NEW.id) THEN
                    RAISE EXCEPTION
                        'categoria % tem subcategorias e não pode virar subcategoria (máximo de dois níveis)',
                        NEW.id
                        USING ERRCODE = '23000';
                END IF;
                IF EXISTS (
                    SELECT 1 FROM cashflow_categories
                    WHERE id = NEW.parent_id AND user_id <> NEW.user_id
                ) THEN
                    RAISE EXCEPTION
                        'categoria %: a categoria pai pertence a outro usuário', NEW.id
                        USING ERRCODE = '23000';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)
    op.execute("""
        CREATE TRIGGER trg_cashflow_categories_depth
        BEFORE INSERT OR UPDATE ON cashflow_categories
        FOR EACH ROW
        EXECUTE FUNCTION enforce_cashflow_category_depth();
        """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_cashflow_categories_depth ON cashflow_categories;")
    op.execute("DROP FUNCTION IF EXISTS enforce_cashflow_category_depth();")
    op.drop_constraint(
        "ck_cashflow_entries_transfer_has_no_category", "cashflow_entries", type_="check"
    )
    op.drop_constraint(
        "fk_cashflow_entries_classified_by_rule_id", "cashflow_entries", type_="foreignkey"
    )
    op.drop_constraint("fk_cashflow_entries_category_id", "cashflow_entries", type_="foreignkey")
    op.drop_index(op.f("ix_cashflow_entries_classified_by_rule_id"), table_name="cashflow_entries")
    op.drop_index(op.f("ix_cashflow_entries_category_id"), table_name="cashflow_entries")
    op.drop_column("cashflow_entries", "classified_by_rule_id")
    op.drop_column("cashflow_entries", "category_id")
    op.drop_table("cashflow_entry_tags")
    op.drop_table("cashflow_rule_tags")
    op.drop_table("cashflow_rules")
    op.drop_table("cashflow_tags")
    op.drop_table("cashflow_categories")
    sa.Enum(name="cashflow_rule_direction").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="cashflow_rule_match_type").drop(op.get_bind(), checkfirst=True)
