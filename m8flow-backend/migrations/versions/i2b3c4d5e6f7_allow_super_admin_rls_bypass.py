"""Allow app-level super-admin RLS bypass via app.bypass_rls session setting.

Revision ID: i2b3c4d5e6f7
Revises: h1a2b3c4d5e6
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "i2b3c4d5e6f7"
down_revision = "h1a2b3c4d5e6"
branch_labels = None
depends_on = None


_RLS_PREDICATE_WITH_BYPASS = (
    "(m8f_tenant_id = current_setting('app.current_tenant', true) "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)
_RLS_PREDICATE_TENANT_ONLY = "(m8f_tenant_id = current_setting('app.current_tenant', true))"


def _policy_names_for_tenant_tables() -> list[str]:
    rows = op.get_bind().execute(
        sa.text(
            """
            SELECT policyname
            FROM pg_policies
            WHERE schemaname = current_schema()
              AND qual LIKE '%m8f_tenant_id = current_setting(''app.current_tenant'', true)%'
            """
        )
    ).fetchall()
    return [str(row[0]) for row in rows]


def _replace_rls_predicate(predicate_sql: str) -> None:
    for policy_name in _policy_names_for_tenant_tables():
        table_name = policy_name.removesuffix("_tenant_rls")
        op.execute(
            sa.text(
                f"ALTER POLICY {policy_name} ON {table_name} "
                f"USING {predicate_sql} "
                f"WITH CHECK {predicate_sql}"
            )
        )


def upgrade() -> None:
    _replace_rls_predicate(_RLS_PREDICATE_WITH_BYPASS)


def downgrade() -> None:
    _replace_rls_predicate(_RLS_PREDICATE_TENANT_ONLY)
