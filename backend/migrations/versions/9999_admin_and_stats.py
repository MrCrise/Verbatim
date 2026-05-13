"""add admin and stats fields

Revision ID: 9999_admin_and_stats
Revises: 8244b0f680af
Create Date: 2026-05-12 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '9999_admin_and_stats'
down_revision = '8244b0f680af'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем колонку последнего входа пользователям
    op.add_column('users', sa.Column('last_login', sa.DateTime(), nullable=True))

    # Добавляем статистику встречам
    op.add_column('meetings', sa.Column('duration_sec', sa.Float(), nullable=True, server_default='0.0'))
    op.add_column('meetings', sa.Column('file_size_bytes', sa.Integer(), nullable=True, server_default='0'))


def downgrade() -> None:
    op.drop_column('meetings', 'file_size_bytes')
    op.drop_column('meetings', 'duration_sec')
    op.drop_column('users', 'last_login')