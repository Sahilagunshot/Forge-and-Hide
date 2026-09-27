"""add razorpay payment id

Revision ID: c506e238db6e
Revises: 5e0896d1ccea
Create Date: 2026-09-06 16:38:01.070988

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c506e238db6e'
down_revision = '5e0896d1ccea'
branch_labels = None
depends_on = None


def upgrade():

    with op.batch_alter_table('orders', schema=None) as batch_op:

        batch_op.add_column(
            sa.Column(
                'razorpay_payment_id',
                sa.String(length=100),
                nullable=True
            )
        )

    op.create_index(
        'uq_orders_razorpay_payment_id',
        'orders',
        ['razorpay_payment_id'],
        unique=True
    )


def downgrade():

    op.drop_index(
        'uq_orders_razorpay_payment_id',
        table_name='orders'
    )

    with op.batch_alter_table('orders', schema=None) as batch_op:

        batch_op.drop_column('razorpay_payment_id')