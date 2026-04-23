"""
SQLite データベースを /tmp/database.db に作成する
"""
import sqlite3

DB_PATH = "/tmp/database.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id         INTEGER PRIMARY KEY,
        name       TEXT    NOT NULL,
        email      TEXT    NOT NULL,
        created_at TEXT    NOT NULL
    )
""")

c.executemany(
    "INSERT INTO users (id, name, email, created_at) VALUES (?, ?, ?, ?)",
    [
        (1, "Alice", "alice@example.com", "2024-01-01"),
        (2, "Bob",   "bob@example.com",   "2024-02-15"),
        (3, "Carol", "carol@example.com", "2024-03-20"),
        (4, "Dave",  "dave@example.com",  "2024-04-10"),
        (5, "Eve",   "eve@example.com",   "2024-05-05"),
    ],
)

conn.commit()
count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
print(f"users テーブルに {count} 件のデータを挿入しました")
conn.close()
print(f"データベースを作成しました: {DB_PATH}")
