"""Persistence and ownership checks for user conversations."""

import json
import sqlite3
import time
from uuid import uuid4

from app.auth import connect_db


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def create_conversation(user_id: str) -> dict[str, str]:
    conversation_id = str(uuid4())
    now = _now_iso()
    with connect_db() as connection:
        connection.execute(
            """
            INSERT INTO conversations (id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, user_id, "New conversation", now, now),
        )

    return {
        "id": conversation_id,
        "thread_id": conversation_id,
        "title": "New conversation",
        "created_at": now,
        "updated_at": now,
    }


def list_conversations(user_id: str) -> list[dict[str, str]]:
    with connect_db() as connection:
        rows = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_owned_conversation(
    user_id: str,
    conversation_id: str,
) -> dict[str, str] | None:
    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE id = ? AND user_id = ?
            """,
            (conversation_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def save_exchange(
    user_id: str,
    conversation_id: str,
    question: str,
    answer: str,
    sources: list[dict],
) -> bool:
    now = _now_iso()
    try:
        with connect_db() as connection:
            row = connection.execute(
                "SELECT id, title FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if row is None:
                return False

            title = row["title"]
            if title == "New conversation":
                title = question.strip().replace("\n", " ")[:80] or title

            connection.execute(
                """
                INSERT INTO messages
                    (id, conversation_id, role, content, sources_json, created_at)
                VALUES (?, ?, 'user', ?, '[]', ?)
                """,
                (str(uuid4()), conversation_id, question, now),
            )
            connection.execute(
                """
                INSERT INTO messages
                    (id, conversation_id, role, content, sources_json, created_at)
                VALUES (?, ?, 'assistant', ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    conversation_id,
                    answer,
                    json.dumps(sources),
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE conversations SET title = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (title, now, conversation_id, user_id),
            )
    except sqlite3.IntegrityError:
        return False
    return True


def get_conversation_messages(
    user_id: str,
    conversation_id: str,
) -> list[dict]:
    with connect_db() as connection:
        rows = connection.execute(
            """
            SELECT messages.role, messages.content, messages.sources_json,
                   messages.created_at
            FROM messages
            JOIN conversations ON conversations.id = messages.conversation_id
            WHERE conversations.id = ? AND conversations.user_id = ?
            ORDER BY messages.created_at, messages.rowid
            """,
            (conversation_id, user_id),
        ).fetchall()
    return [
        {
            "role": row["role"],
            "content": row["content"],
            "sources": json.loads(row["sources_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def delete_owned_conversation(user_id: str, conversation_id: str) -> bool:
    with connect_db() as connection:
        cursor = connection.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
    return cursor.rowcount == 1
