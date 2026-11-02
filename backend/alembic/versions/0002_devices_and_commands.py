"""Add device registry and idempotent LED command storage.

Revision ID: 0002_devices_and_commands
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_devices_and_commands"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _create_table_if_missing(name, *args, **kwargs):
    if op.get_context().as_sql or not sa.inspect(op.get_bind()).has_table(name):
        op.create_table(name, *args, **kwargs)


def _create_index_if_missing(name, table, columns):
    if op.get_context().as_sql:
        op.create_index(name, table, columns, unique=False)
    elif not sa.inspect(op.get_bind()).has_index(table, name):
        op.create_index(name, table, columns, unique=False)


def upgrade():
    # 0001 imports live ORM metadata, so a fresh run may already contain these
    # tables. Existing databases stamped at 0001 may not. Create only what is missing.
    _create_table_if_missing(
        "devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_identifier", sa.String(length=128), nullable=False),
        sa.Column("device_name", sa.String(length=160), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "credential_hash",
            sa.String(length=128),
            nullable=False,
            comment="One-way credential verifier only; never store the raw device token.",
        ),
        sa.Column("credential_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("credential_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credential_revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(trim(device_identifier)) > 0", name="ck_devices_identifier_nonempty"),
        sa.CheckConstraint("length(trim(device_name)) > 0", name="ck_devices_name_nonempty"),
        sa.CheckConstraint("credential_version >= 1", name="ck_devices_credential_version_positive"),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], name="fk_devices_plant_id_plants", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_devices"),
        sa.UniqueConstraint("credential_hash", name="uq_devices_credential_hash"),
        sa.UniqueConstraint("device_identifier", name="uq_devices_device_identifier"),
        sa.UniqueConstraint("id", "plant_id", name="uq_devices_id_plant_id"),
    )
    _create_index_if_missing("ix_devices_plant_id", "devices", ["plant_id"])
    _create_index_if_missing("ix_devices_enabled_last_seen", "devices", ["enabled", "last_seen_at"])

    _create_table_if_missing(
        "device_commands",
        sa.Column("command_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("led_channel", sa.String(length=4), nullable=False),
        sa.Column("desired_state", sa.String(length=3), nullable=False),
        sa.Column("command_source", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=12), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column(
            "failure_detail",
            sa.String(length=255),
            nullable=True,
            comment="Short sanitized failure detail only; no credentials or raw stack traces.",
        ),
        sa.CheckConstraint("led_channel IN ('LED1', 'LED2')", name="ck_device_commands_led_channel"),
        sa.CheckConstraint("desired_state IN ('ON', 'OFF')", name="ck_device_commands_desired_state"),
        sa.CheckConstraint(
            "(led_channel = 'LED1' AND command_source = 'WATERING_ASSISTANT') OR "
            "(led_channel = 'LED2' AND command_source = 'DISEASE_DETECTION')",
            name="ck_device_commands_channel_source",
        ),
        sa.CheckConstraint("status IN ('PENDING', 'DELIVERED', 'ACKNOWLEDGED', 'FAILED', 'EXPIRED')", name="ck_device_commands_status"),
        sa.CheckConstraint("length(trim(command_source)) > 0", name="ck_device_commands_source_nonempty"),
        sa.CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_device_commands_idempotency_nonempty"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_device_commands_attempt_count_nonnegative"),
        sa.CheckConstraint("expires_at > created_at", name="ck_device_commands_expiry_after_creation"),
        sa.CheckConstraint("acknowledged_at IS NULL OR delivered_at IS NOT NULL", name="ck_device_commands_ack_requires_delivery"),
        sa.CheckConstraint("status != 'DELIVERED' OR delivered_at IS NOT NULL", name="ck_device_commands_delivered_timestamp"),
        sa.CheckConstraint("status != 'ACKNOWLEDGED' OR acknowledged_at IS NOT NULL", name="ck_device_commands_ack_timestamp"),
        sa.CheckConstraint("status != 'FAILED' OR failure_code IS NOT NULL", name="ck_device_commands_failure_code"),
        sa.ForeignKeyConstraint(
            ["device_id", "plant_id"],
            ["devices.id", "devices.plant_id"],
            name="fk_device_commands_device_plant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], name="fk_device_commands_plant", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("command_id", name="pk_device_commands"),
        sa.UniqueConstraint("device_id", "idempotency_key", name="uq_device_commands_device_idempotency"),
    )
    _create_index_if_missing("ix_device_commands_plant_id", "device_commands", ["plant_id"])
    _create_index_if_missing("ix_device_commands_device_status_created", "device_commands", ["device_id", "status", "created_at"])
    _create_index_if_missing("ix_device_commands_status_expires", "device_commands", ["status", "expires_at"])


def downgrade():
    op.drop_index("ix_device_commands_status_expires", table_name="device_commands")
    op.drop_index("ix_device_commands_device_status_created", table_name="device_commands")
    op.drop_index("ix_device_commands_plant_id", table_name="device_commands")
    op.drop_table("device_commands")
    op.drop_index("ix_devices_enabled_last_seen", table_name="devices")
    op.drop_index("ix_devices_plant_id", table_name="devices")
    op.drop_table("devices")
