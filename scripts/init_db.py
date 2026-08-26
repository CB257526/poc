"""初始化数据库并写入种子账号。"""

from workflows.backend.database import SessionLocal, init_db
from workflows.backend.seed import seed_users
from workflows.backend.config_store import ensure_config_rows


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_users(db)
        ensure_config_rows(db)
        print("database ready: runtime/backend.db")
        print("seed users: admin@byd.local / operator@byd.local / finance@byd.local / viewer@byd.local")
        print("password: Passw0rd!")
    finally:
        db.close()


if __name__ == "__main__":
    main()
