"""MySQL 연결 헬퍼 (PyMySQL 기반).

- ``.env`` / docker-compose 의 ``MYSQL_*`` 환경변수를 그대로 사용.
- 짧은 작업 단위에 맞도록 ``with get_conn() as cur:`` 컨텍스트 매니저 제공.
- 본 모듈은 *얇은* 래퍼이며 ORM 을 도입하지 않는다 (Step 5 범위).
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor

log = logging.getLogger(__name__)

_MYSQL_CONFIG = {
    "host":     os.getenv("MYSQL_HOST", "mysql"),
    "port":     int(os.getenv("MYSQL_PORT", "3306")),
    "user":     os.getenv("MYSQL_USER", "localai"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "localai_db"),
    "charset":  "utf8mb4",
    "autocommit": False,
    "cursorclass": DictCursor,
}


def connect() -> pymysql.connections.Connection:
    return pymysql.connect(**_MYSQL_CONFIG)


@contextmanager
def get_cursor(commit: bool = True) -> Iterator[DictCursor]:
    """간단한 트랜잭션 래퍼."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(sql: str, params: tuple | dict | None = None) -> int:
    """INSERT 후 ``lastrowid`` 또는 affected rows 반환."""
    with get_cursor() as cur:
        cur.execute(sql, params or ())
        return cur.lastrowid or cur.rowcount


def fetch_one(sql: str, params: tuple | dict | None = None) -> dict[str, Any] | None:
    with get_cursor(commit=False) as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def ping() -> bool:
    try:
        conn = connect()
        try:
            conn.ping(reconnect=False)
            return True
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("mysql ping failed: %s", exc)
        return False
