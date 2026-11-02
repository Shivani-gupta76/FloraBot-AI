"""Add optional camera upload retry idempotency records.

Revision ID: 0003_camera_upload_idempotency
Revises: 0002_devices_and_commands
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_camera_upload_idempotency"
down_revision = "0002_devices_and_commands"
branch_labels = None
depends_on = None


def upgrade():
    # The 0001 baseline creates current ORM metadata. A fresh install may already
    # have this table; databases with an older stamped baseline will not.
    offline_sql = op.get_context().as_sql
    inspector = sa.inspect(op.get_bind()) if not offline_sql else None
    if offline_sql or not inspector.has_table("camera_upload_requests"):
        op.create_table(
            "camera_upload_requests",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("plant_id", sa.Integer(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("image_sha256", sa.String(length=64), nullable=False),
            sa.Column("detection_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_camera_upload_key_nonempty"),
            sa.CheckConstraint("length(image_sha256) = 64", name="ck_camera_upload_hash_length"),
            sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], name="fk_camera_upload_plant", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["detection_id"], ["disease_detections.id"], name="fk_camera_upload_detection", ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id", name="pk_camera_upload_requests"),
            sa.UniqueConstraint("plant_id", "idempotency_key", name="uq_camera_upload_plant_key"),
            sa.UniqueConstraint("detection_id", name="uq_camera_upload_detection"),
        )
    if offline_sql or not any(
        constraint.get("name") == "ck_device_commands_channel_source"
        for constraint in sa.inspect(op.get_bind()).get_check_constraints("device_commands")
    ):
        if not offline_sql:
            invalid_rows = op.get_bind().execute(
                sa.text(
                    "SELECT count(*) FROM device_commands WHERE NOT ("
                    "(led_channel = 'LED1' AND command_source = 'WATERING_ASSISTANT') OR "
                    "(led_channel = 'LED2' AND command_source = 'DISEASE_DETECTION'))"
                )
            ).scalar_one()
            if invalid_rows:
                raise RuntimeError("Existing device commands violate the LED channel/source rule; review rows before migration.")
        op.create_check_constraint(
            "ck_device_commands_channel_source",
            "device_commands",
            "(led_channel = 'LED1' AND command_source = 'WATERING_ASSISTANT') OR "
            "(led_channel = 'LED2' AND command_source = 'DISEASE_DETECTION')",
        )
    if offline_sql or not sa.inspect(op.get_bind()).has_index("camera_upload_requests", "ix_camera_upload_created_at"):
        op.create_index("ix_camera_upload_created_at", "camera_upload_requests", ["created_at"], unique=False)


def downgrade():
    op.drop_index("ix_camera_upload_created_at", table_name="camera_upload_requests")
    op.drop_table("camera_upload_requests")
