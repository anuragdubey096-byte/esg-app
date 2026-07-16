"""Add portfolios, funds, and attributed holdings.

Revision ID: 20260716_03
Revises: 20260715_02
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_03"
down_revision: str | None = "20260715_02"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'portfolios',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('base_currency', sa.String(), nullable=False, server_default='USD'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('code'),
    )
    op.create_index(op.f('ix_portfolios_id'), 'portfolios', ['id'])
    op.create_index(op.f('ix_portfolios_code'), 'portfolios', ['code'], unique=True)
    op.create_table(
        'funds',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('portfolio_id', sa.Integer(), sa.ForeignKey('portfolios.id'), nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('vintage_year', sa.Integer(), nullable=True),
        sa.Column('base_currency', sa.String(), nullable=False, server_default='USD'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('portfolio_id', 'code', name='uq_fund_portfolio_code'),
    )
    op.create_index(op.f('ix_funds_id'), 'funds', ['id'])
    op.create_index(op.f('ix_funds_portfolio_id'), 'funds', ['portfolio_id'])
    op.create_table(
        'holdings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fund_id', sa.Integer(), sa.ForeignKey('funds.id'), nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('external_id', sa.String(), nullable=False),
        sa.Column('ownership_percent', sa.Float(), nullable=False),
        sa.Column('invested_amount_base', sa.Float(), nullable=False, server_default='0'),
        sa.Column('nav_value_base', sa.Float(), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(), nullable=False, server_default='USD'),
        sa.Column('effective_from', sa.String(), nullable=False),
        sa.Column('effective_to', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('fund_id', 'external_id', name='uq_holding_fund_external_id'),
        sa.CheckConstraint('ownership_percent > 0 AND ownership_percent <= 100', name='ck_holding_ownership_range'),
        sa.CheckConstraint('invested_amount_base >= 0 AND nav_value_base >= 0', name='ck_holding_values_nonnegative'),
    )
    op.create_index(op.f('ix_holdings_id'), 'holdings', ['id'])
    op.create_index(op.f('ix_holdings_fund_id'), 'holdings', ['fund_id'])
    op.create_index(op.f('ix_holdings_company_id'), 'holdings', ['company_id'])


def downgrade() -> None:
    op.drop_table('holdings')
    op.drop_table('funds')
    op.drop_table('portfolios')
