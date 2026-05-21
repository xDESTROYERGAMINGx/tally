import json
import os
import sqlite3


class Database:
    def __init__(self):
        self.conn = sqlite3.connect("survey_vault.db")
        self.cur = self.conn.cursor()
        self.cur.execute(
            """CREATE TABLE IF NOT EXISTS sessions
            (id INTEGER PRIMARY KEY, date TEXT, tally TEXT)"""
        )
        self.cur.execute(
            """CREATE TABLE IF NOT EXISTS images
            (id INTEGER PRIMARY KEY, session_id INTEGER, path TEXT, result TEXT)"""
        )
        self._ensure_column("sessions", "question_tally", "TEXT", "{}")
        self._ensure_column("sessions", "config", "TEXT", "{}")
        self.conn.commit()

    def _ensure_column(self, table, column, column_type, default_value):
        existing_columns = [
            row[1]
            for row in self.cur.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        if column not in existing_columns:
            self.cur.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {column_type} "
                f"DEFAULT '{default_value}'"
            )

    def start_session(self, date_str):
        self.cur.execute(
            "INSERT INTO sessions (date, tally, question_tally, config) "
            "VALUES (?, ?, ?, ?)",
            (date_str, "{}", "{}", "{}"),
        )
        self.conn.commit()
        return self.cur.lastrowid

    def add_scan_to_session(
        self,
        session_id,
        img_path,
        result_dict,
        current_tally,
        question_tally=None,
        config=None,
    ):
        self.cur.execute(
            "INSERT INTO images (session_id, path, result) VALUES (?, ?, ?)",
            (session_id, img_path, json.dumps(result_dict)),
        )
        self.cur.execute(
            "UPDATE sessions SET tally = ?, question_tally = ?, config = ? "
            "WHERE id = ?",
            (
                json.dumps(current_tally),
                json.dumps(question_tally or {}),
                json.dumps(config or {}),
                session_id,
            ),
        )
        self.conn.commit()

    def get_all_sessions(self):
        return self.cur.execute(
            "SELECT id, date, tally, question_tally, config "
            "FROM sessions ORDER BY id DESC"
        ).fetchall()

    def get_session(self, session_id):
        return self.cur.execute(
            "SELECT id, date, tally, question_tally, config "
            "FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

    def get_session_images(self, session_id):
        return self.cur.execute(
            "SELECT path, result FROM images WHERE session_id = ?",
            (session_id,),
        ).fetchall()

    def count_session_images(self, session_id):
        row = self.cur.execute(
            "SELECT COUNT(*) FROM images WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row[0] if row else 0

    def delete_session(self, session_id, owned_root=None):
        imgs = self.get_session_images(session_id)
        safe_root = os.path.abspath(owned_root) if owned_root else None
        for img_path, _ in imgs:
            image_path = os.path.abspath(img_path)
            try:
                is_owned_copy = (
                    safe_root is not None
                    and os.path.commonpath([safe_root, image_path]) == safe_root
                )
            except ValueError:
                is_owned_copy = False
            if is_owned_copy and os.path.exists(image_path):
                os.remove(image_path)
        self.cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self.cur.execute("DELETE FROM images WHERE session_id = ?", (session_id,))
        self.conn.commit()
