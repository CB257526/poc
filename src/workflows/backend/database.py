"""SQLite 会话。"""

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from workflows.paths import runtime_dir


class Base(DeclarativeBase):
    pass


def _database_path():
    return runtime_dir() / "backend.db"


DATABASE_URL = f"sqlite:///{_database_path()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _sqlite_on_connect(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    from . import models  # noqa: F401

    runtime_dir()
    Base.metadata.create_all(bind=engine)


def _schema_ready() -> bool:
    try:
        names = set(inspect(engine).get_table_names())
    except Exception:
        return False
    return {"users", "tasks", "config_files", "exceptions"}.issubset(names)


def ensure_db() -> None:
    """目录或库文件被清掉时，把表建回来并补种子。"""
    if _schema_ready():
        return
    init_db()
    from .config_store import ensure_config_rows
    from .seed import seed_users

    db = SessionLocal()
    try:
        seed_users(db)
        ensure_config_rows(db)
    finally:
        db.close()


def get_db():
    ensure_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
