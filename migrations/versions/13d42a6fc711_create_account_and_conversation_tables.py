"""create account and conversation tables

Revision ID: 13d42a6fc711
Revises:
Create Date: 2026-11-06 01:24:45.602929

"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '13d42a6fc711'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_TABLES = (
    "users",
    "auth_sessions",
    "auth_rate_limits",
    "conversations",
    "messages",
)
LEGACY_PREFIX = "_medibot_legacy_"


def _is_legacy_schema(connection) -> bool:
    inspector = sa.inspect(connection)
    if "users" not in inspector.get_table_names():
        return False
    columns = {column["name"] for column in inspector.get_columns("users")}
    return {"name", "email", "password_hash"}.issubset(columns)


def _legacy_database_path() -> Path:
    configured_path = os.getenv("MEDIBOT_AUTH_DB_PATH")
    if configured_path:
        return Path(configured_path).resolve()
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "data" / "medibot_auth.sqlite3"


def _parse_legacy_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _execute_source(connection, source, statement: str):
    if source is connection:
        return source.execute(sa.text(statement))
    return source.execute(statement)


def _import_legacy_data(connection, source, table_prefix: str = "") -> None:
    source_tables = {
        row[0]
        for row in _execute_source(
            connection,
            source,
            "SELECT name FROM sqlite_master WHERE type = 'table'",
        )
    }
    required_tables = {
        f"{table_prefix}{table_name}"
        for table_name in ("users", "conversations", "messages")
    }
    if not required_tables.issubset(source_tables):
        return

    users_table = sa.table(
        "users",
        sa.column("id", sa.String),
        sa.column("name", sa.Text),
        sa.column("email", sa.String),
        sa.column("password_hash", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    conversations_table = sa.table(
        "conversations",
        sa.column("id", sa.String),
        sa.column("owner_id", sa.String),
        sa.column("title", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    messages_table = sa.table(
        "conversation_messages",
        sa.column("conversation_id", sa.String),
        sa.column("role", sa.String),
        sa.column("content", sa.Text),
        sa.column("sources", sa.JSON),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    if source is not connection:
        source.execute("BEGIN")
    try:
        for row in _execute_source(
            connection,
            source,
            f"SELECT id, name, email, password_hash, created_at "
            f"FROM {table_prefix}users",
        ):
            connection.execute(
                users_table.insert(),
                {
                    "id": row[0],
                    "name": row[1],
                    "email": row[2],
                    "password_hash": row[3],
                    "created_at": _parse_legacy_timestamp(row[4]),
                },
            )

        for row in _execute_source(
            connection,
            source,
            f"SELECT id, user_id, title, created_at, updated_at "
            f"FROM {table_prefix}conversations",
        ):
            connection.execute(
                conversations_table.insert(),
                {
                    "id": row[0],
                    "owner_id": row[1],
                    "title": row[2],
                    "created_at": _parse_legacy_timestamp(row[3]),
                    "updated_at": _parse_legacy_timestamp(row[4]),
                },
            )

        for row in _execute_source(
            connection,
            source,
            f"SELECT conversation_id, role, content, sources_json, created_at "
            f"FROM {table_prefix}messages ORDER BY created_at, rowid",
        ):
            sources = json.loads(row[3] or "[]")
            if not isinstance(sources, list):
                raise ValueError("Legacy message sources must be a JSON array.")
            connection.execute(
                messages_table.insert(),
                {
                    "conversation_id": row[0],
                    "role": row[1],
                    "content": row[2],
                    "sources": sources,
                    "created_at": _parse_legacy_timestamp(row[4]),
                },
            )
    finally:
        if source is not connection:
            source.rollback()


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()
    legacy_in_target = (
        connection.dialect.name == "sqlite" and _is_legacy_schema(connection)
    )
    if legacy_in_target:
        for table_name in LEGACY_TABLES:
            if table_name in sa.inspect(connection).get_table_names():
                op.rename_table(table_name, f"{LEGACY_PREFIX}{table_name}")

    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('rate_limit_buckets',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('hits', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('users',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=512), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    op.create_table('auth_sessions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('auth_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_auth_sessions_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_auth_sessions_token_hash'), ['token_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_auth_sessions_user_id'), ['user_id'], unique=False)

    op.create_table('conversations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('owner_id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_conversations_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_conversations_updated_at'), ['updated_at'], unique=False)

    op.create_table('conversation_messages',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('conversation_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('sources', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('conversation_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_conversation_messages_conversation_id'), ['conversation_id'], unique=False)

    # ### end Alembic commands ###
    if legacy_in_target:
        _import_legacy_data(
            connection,
            connection,
            table_prefix=LEGACY_PREFIX,
        )
        for table_name in reversed(LEGACY_TABLES):
            legacy_name = f"{LEGACY_PREFIX}{table_name}"
            if legacy_name in sa.inspect(connection).get_table_names():
                op.drop_table(legacy_name)
    else:
        legacy_path = _legacy_database_path()
        target_path = getattr(connection.engine.url, "database", None)
        if (
            legacy_path.is_file()
            and not (
                connection.dialect.name == "sqlite"
                and target_path
                and legacy_path == Path(target_path).resolve()
            )
        ):
            source = sqlite3.connect(legacy_path.as_uri() + "?mode=ro", uri=True)
            try:
                _import_legacy_data(connection, source)
            finally:
                source.close()


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('conversation_messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_conversation_messages_conversation_id'))

    op.drop_table('conversation_messages')
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_conversations_updated_at'))
        batch_op.drop_index(batch_op.f('ix_conversations_owner_id'))

    op.drop_table('conversations')
    with op.batch_alter_table('auth_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_auth_sessions_user_id'))
        batch_op.drop_index(batch_op.f('ix_auth_sessions_token_hash'))
        batch_op.drop_index(batch_op.f('ix_auth_sessions_expires_at'))

    op.drop_table('auth_sessions')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
    op.drop_table('rate_limit_buckets')
    # ### end Alembic commands ###
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        table_names = set(sa.inspect(connection).get_table_names())
        for table_name in reversed(LEGACY_TABLES):
            legacy_name = f"{LEGACY_PREFIX}{table_name}"
            if legacy_name in table_names:
                op.rename_table(legacy_name, table_name)
