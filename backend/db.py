"""MySQL 연결 헬퍼 (SQLAlchemy 커넥션 풀 기반).

- ``.env`` / docker-compose 의 ``MYSQL_*`` 환경변수를 그대로 사용.
- SQLAlchemy ``QueuePool`` 로 커넥션을 재사용하고, 끊어진 연결은 자동으로
  ``pool_pre_ping`` 으로 검사 후 재연결한다.
- 기존 호출부(``execute`` / ``fetch_one`` / ``fetch_all`` / ``get_cursor`` /
  ``connect`` / ``ping``) API 는 그대로 유지하므로 backend 호출 코드는
  수정할 필요가 없다.

ENV
---
- MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
- DB_POOL_SIZE          : 풀이 항상 유지하는 커넥션 수 (default 5)
- DB_MAX_OVERFLOW       : 피크 시 추가로 열 수 있는 커넥션 수 (default 10)
- DB_POOL_RECYCLE_SEC   : 이 초가 지난 커넥션은 재생성 (default 1800)
- DB_POOL_TIMEOUT_SEC   : 풀에서 커넥션을 받기까지 대기 (default 30)
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import quote_plus

import pymysql  # noqa: F401  # PyMySQL DBAPI
from pymysql.cursors import DictCursor

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import QueuePool

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
_HOST     = os.getenv("MYSQL_HOST", "mysql")
_PORT     = int(os.getenv("MYSQL_PORT", "3306"))
_USER     = os.getenv("MYSQL_USER", "localai")
_DATABASE = os.getenv("MYSQL_DATABASE", "localai_db")

# 비밀번호는 빈 문자열을 허용하지 않는다 (보안).
# 단위 테스트 등에서 의도적으로 비활성화하려면 ALLOW_EMPTY_DB_PASSWORD=1.
_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
if not _PASSWORD and os.getenv("ALLOW_EMPTY_DB_PASSWORD", "").lower() not in ("1", "true", "yes"):
    raise RuntimeError(
        "MYSQL_PASSWORD is empty. Set it in .env "
        "(or export ALLOW_EMPTY_DB_PASSWORD=1 to bypass for local testing only)."
    )

_POOL_SIZE        = int(os.getenv("DB_POOL_SIZE", "5"))
_MAX_OVERFLOW     = int(os.getenv("DB_MAX_OVERFLOW", "10"))
_POOL_RECYCLE_SEC = int(os.getenv("DB_POOL_RECYCLE_SEC", "1800"))
_POOL_TIMEOUT_SEC = int(os.getenv("DB_POOL_TIMEOUT_SEC", "30"))


def _build_url() -> str:
    pw = quote_plus(_PASSWORD)  # 비밀번호 특수문자 안전 처리
    return (
        f"mysql+pymysql://{_USER}:{pw}@{_HOST}:{_PORT}/{_DATABASE}"
        f"?charset=utf8mb4"
    )


# ---------------------------------------------------------------------------
# Engine (lazy singleton)
# ---------------------------------------------------------------------------
_engine: Engine | None = None
_engine_lock = threading.Lock()


def get_engine() -> Engine:
    """프로세스 단일 SQLAlchemy Engine 반환 (lazy init)."""
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is not None:
            return _engine
        _engine = create_engine(
            _build_url(),
            poolclass=QueuePool,
            pool_size=_POOL_SIZE,
            max_overflow=_MAX_OVERFLOW,
            pool_recycle=_POOL_RECYCLE_SEC,
            pool_timeout=_POOL_TIMEOUT_SEC,
            pool_pre_ping=True,
            future=True,
            echo=os.getenv("DB_ECHO", "").lower() in ("1", "true", "yes"),
        )
        log.info(
            "SQLAlchemy engine ready host=%s db=%s pool_size=%d max_overflow=%d",
            _HOST, _DATABASE, _POOL_SIZE, _MAX_OVERFLOW,
        )
        return _engine


def dispose_engine() -> None:
    """프로세스 종료 시 호출하면 모든 커넥션을 안전하게 닫는다."""
    global _engine
    with _engine_lock:
        if _engine is not None:
            try:
                _engine.dispose()
            finally:
                _engine = None


# ---------------------------------------------------------------------------
# 호환 API (기존 PyMySQL 인터페이스 유지)
# ---------------------------------------------------------------------------
def connect():
    """풀에서 raw PyMySQL connection 을 하나 꺼낸다.

    반환값을 ``.close()`` 하면 실제로 닫지 않고 풀로 반환된다
    (SQLAlchemy ``_ConnectionFairy`` 동작).
    """
    return get_engine().raw_connection()


@contextmanager
def get_cursor(commit: bool = True) -> Iterator[DictCursor]:
    """간단한 트랜잭션 래퍼 (DictCursor)."""
    conn = connect()
    try:
        cur = conn.cursor(DictCursor)
        try:
            yield cur
        finally:
            cur.close()
        if commit:
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        conn.close()  # 풀로 반환


def execute(sql: str, params: tuple | dict | None = None) -> int:
    """INSERT 후 ``lastrowid`` 또는 affected rows 반환."""
    with get_cursor() as cur:
        cur.execute(sql, params or ())
        return cur.lastrowid or cur.rowcount


def fetch_one(sql: str, params: tuple | dict | None = None) -> dict[str, Any] | None:
    with get_cursor(commit=False) as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def fetch_all(sql: str, params: tuple | dict | None = None) -> list[dict[str, Any]]:
    with get_cursor(commit=False) as cur:
        cur.execute(sql, params or ())
        return list(cur.fetchall())


def ping() -> bool:
    """DB 응답 여부. 풀에서 커넥션을 빌려 SELECT 1 을 실행한다."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, Exception) as exc:  # noqa: BLE001
        log.warning("mysql ping failed: %s", exc)
        return False


def pool_status() -> dict[str, Any]:
    """현재 커넥션 풀 사용 현황 (모니터링용)."""
    pool = get_engine().pool
    out: dict[str, Any] = {
        "pool_size":    _POOL_SIZE,
        "max_overflow": _MAX_OVERFLOW,
    }
    for attr in ("size", "checkedin", "checkedout", "overflow"):
        fn = getattr(pool, attr, None)
        if callable(fn):
            try:
                out[attr] = fn()
            except Exception:  # noqa: BLE001
                out[attr] = None
    return out
