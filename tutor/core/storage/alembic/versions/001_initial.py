"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-08

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create workflow_runs table
    op.create_table(
        'workflow_runs',
        sa.Column('run_id', sa.String(64), primary_key=True),
        sa.Column('workflow_type', sa.String(32), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, default='pending'),
        sa.Column('params', sa.Text, nullable=True),
        sa.Column('config', sa.Text, nullable=True),
        sa.Column('started_at', sa.DateTime, nullable=True),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('result', sa.Text, nullable=True),
        sa.Column('error', sa.Text, nullable=True),
        sa.Column('usage', sa.Text, nullable=True),
        sa.Column('tags', sa.Text, default='[]'),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )

    op.create_index('idx_runs_status', 'workflow_runs', ['status'])
    op.create_index('idx_runs_type', 'workflow_runs', ['workflow_type'])

    # Create run_events table
    op.create_table(
        'run_events',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('run_id', sa.String(64), sa.ForeignKey('workflow_runs.run_id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(32), nullable=False),
        sa.Column('event_data', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )

    op.create_index('idx_events_run', 'run_events', ['run_id'])


def downgrade():
    op.drop_table('run_events')
    op.drop_table('workflow_runs')
