"""add country to orders

Revision ID: e90bb2060502
Revises: c506e238db6e
Create Date: 2026-11-22 17:43:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e90bb2060502'
down_revision = 'c506e238db6e'
branch_labels = None
depends_on = None


def upgrade():

    with op.batch_alter_table('orders', schema=None) as batch_op:

        batch_op.add_column(
            sa.Column(
                'country',
                sa.String(length=100),
                nullable=True
            )
        )


def downgrade():

    with op.batch_alter_table('orders', schema=None) as batch_op:

        batch_op.drop_column('country')




    op.create_table('hero_slides',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('product_id', sa.INTEGER(), nullable=True),
    sa.Column('title', sa.VARCHAR(length=200), nullable=True),
    sa.Column('subtitle', sa.VARCHAR(length=200), nullable=True),
    sa.Column('button_text', sa.VARCHAR(length=60), nullable=True),
    sa.Column('link', sa.VARCHAR(length=300), nullable=True),
    sa.Column('image', sa.VARCHAR(length=300), nullable=True),
    sa.Column('sort_order', sa.INTEGER(), nullable=True),
    sa.Column('is_active', sa.BOOLEAN(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('site_settings',
    sa.Column('key', sa.VARCHAR(length=100), nullable=False),
    sa.Column('value', sa.TEXT(), nullable=True),
    sa.PrimaryKeyConstraint('key')
    )
    # ### end Alembic commands ###
