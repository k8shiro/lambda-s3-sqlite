import json
import logging
import os
import sqlite3
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DB_PATH = os.environ.get("DB_PATH", "/mnt/s3data/database.db")


def lambda_handler(event, context):
    action = event.get("action", "query_users")
    logger.info(f"action={action}, db_path={DB_PATH}")

    if not os.path.exists(DB_PATH):
        logger.error(f"データベースが見つかりません: {DB_PATH}")
        return {
            "statusCode": 500,
            "body": f"データベースが見つかりません: {DB_PATH}",
        }

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        if action == "query_users":
            # ユーザー一覧を取得する（読み取りテスト）
            rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
            users = [dict(row) for row in rows]
            logger.info(f"{len(users)} 件のユーザーを取得しました")
            return {
                "statusCode": 200,
                "body": {
                    "users": users,
                    "count": len(users),
                    "db_path": DB_PATH,
                },
            }

        elif action == "db_info":
            # DB のメタ情報を返す
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            return {
                "statusCode": 200,
                "body": {
                    "tables": [t["name"] for t in tables],
                    "db_path": DB_PATH,
                    "db_size_bytes": os.path.getsize(DB_PATH),
                },
            }

        elif action == "insert_user":
            # ユーザーを1件 INSERT する（書き込みテスト）
            name = event.get("name", "TestUser")
            email = event.get("email", "test@example.com")
            created_at = event.get("created_at", time.strftime("%Y-%m-%d"))

            conn.execute(
                "INSERT INTO users (name, email, created_at) VALUES (?, ?, ?)",
                (name, email, created_at),
            )
            conn.commit()

            new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            logger.info(f"INSERT 完了: id={new_id}, 合計={count}件")
            return {
                "statusCode": 200,
                "body": {
                    "inserted_id": new_id,
                    "total_count": count,
                },
            }

        elif action == "concurrent_write":
            # 同時書き込みテスト用: 少し待ってから INSERT する
            # 複数の Lambda を同時に起動したときの競合を観察する
            delay = event.get("delay_ms", 0)
            label = event.get("label", "unknown")

            if delay > 0:
                time.sleep(delay / 1000)

            start = time.time()
            conn.execute(
                "INSERT INTO users (name, email, created_at) VALUES (?, ?, ?)",
                (f"concurrent_{label}", f"{label}@example.com", time.strftime("%Y-%m-%d")),
            )
            conn.commit()
            elapsed_ms = int((time.time() - start) * 1000)

            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            logger.info(f"concurrent_write: label={label}, commit={elapsed_ms}ms, total={count}")
            return {
                "statusCode": 200,
                "body": {
                    "label": label,
                    "commit_ms": elapsed_ms,
                    "total_count": count,
                },
            }

        elif action == "write_then_read":
            # 書き込み直後に同じ接続で読み返すテスト
            # NFS マウント越しでも即座に読み取れるか確認する
            name = event.get("name", "ImmediateReadUser")
            email = event.get("email", "immediate@example.com")
            created_at = time.strftime("%Y-%m-%d")

            conn.execute(
                "INSERT INTO users (name, email, created_at) VALUES (?, ?, ?)",
                (name, email, created_at),
            )
            conn.commit()
            new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # 同じ接続でそのまま SELECT
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (new_id,)
            ).fetchone()
            all_rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()

            logger.info(f"write_then_read: inserted id={new_id}, immediately readable={row is not None}")
            return {
                "statusCode": 200,
                "body": {
                    "inserted_id": new_id,
                    "immediately_readable": row is not None,
                    "inserted_row": dict(row) if row else None,
                    "total_count": len(all_rows),
                },
            }

        else:
            return {"statusCode": 400, "body": f"不明なアクション: {action}"}

    finally:
        conn.close()
