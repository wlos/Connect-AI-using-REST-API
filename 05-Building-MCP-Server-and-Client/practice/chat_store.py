"""Persist the weather chatbot's conversations in a local SQLite database."""

import json
import sqlite3
from contextlib import closing


class ChatStore:
    def __init__(self, filename: str):
        self.filename = filename
        with closing(self.connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    browser_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    conversation TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS chats_by_browser ON chats(browser_id, updated_at)")

    def connect(self):
        db = sqlite3.connect(self.filename)
        db.row_factory = sqlite3.Row
        return db

    def list(self, browser_id: str):
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT id, title FROM chats WHERE browser_id = ? ORDER BY updated_at DESC, rowid DESC",
                (browser_id,),
            )
            return [dict(row) for row in rows]

    def read(self, browser_id: str, chat_id: str):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT title, messages, conversation FROM chats WHERE id = ? AND browser_id = ?",
                (chat_id, browser_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "title": row["title"],
            "messages": json.loads(row["messages"]),
            "conversation": json.loads(row["conversation"]),
        }

    def save(self, browser_id: str, chat_id: str, title: str, messages: list, conversation: list):
        # Store the visible transcript and the model's tool messages in one transaction.
        with closing(self.connect()) as db, db:
            db.execute("""
                INSERT INTO chats (id, browser_id, title, messages, conversation, updated_at)
                VALUES (?, ?, ?, ?, ?, STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'now'))
                ON CONFLICT(id) DO UPDATE SET
                    messages = excluded.messages,
                    conversation = excluded.conversation,
                    updated_at = excluded.updated_at
                WHERE chats.browser_id = excluded.browser_id
            """, (chat_id, browser_id, title, json.dumps(messages), json.dumps(conversation)))
