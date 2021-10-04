"""Add machine tables

Revision ID: c343c2fad603
Revises: 
Create Date: 2021-09-24 10:19:10.538882

"""
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c343c2fad603'
down_revision = None
branch_labels = None
depends_on = None


def upgrade(op=None):
    op.create_table(
        "machine_chall_model",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("slug", sa.Text(25), unique=True),
        sa.Column("duration", sa.Integer, default=60),
        sa.Column("config", sa.Text()),
        sa.ForeignKeyConstraint(["id"], ["dynamic_challenge.id"], ondelete="CASCADE")
    )
    op.create_table(
        "machine_log_model",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("chall_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(255)),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("time_str", sa.DateTime(), nullable=False),
        sa.Column("time_end", sa.DateTime(), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chall_id"], ["challenges.id"], ondelete="CASCADE"),
    )

def downgrade(op=None):
    op.drop_table("machine_log_model")
    op.drop_table("machine_chall_model")