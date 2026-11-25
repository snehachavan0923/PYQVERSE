import json
from types import SimpleNamespace

from fastapi import Request
from sqlalchemy.exc import ProgrammingError

from app.main import unhandled_exception_handler


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/admin/uploads",
            "raw_path": b"/api/v1/admin/uploads",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        }
    )


def test_schema_programming_error_returns_sanitized_500():
    sql = "SELECT private_column FROM private_table"
    error = ProgrammingError(sql, {}, SimpleNamespace(sqlstate="42703"))

    response = _run_handler(error)

    assert response.status_code == 500
    assert json.loads(response.body) == {
        "code": "DATABASE_SCHEMA_ERROR",
        "detail": "The server's data schema is out of date. Please contact an administrator.",
    }
    assert sql.encode() not in response.body


def test_other_unhandled_error_returns_generic_sanitized_500():
    response = _run_handler(RuntimeError("sensitive diagnostic"))

    assert response.status_code == 500
    assert b"sensitive diagnostic" not in response.body
    assert b"INTERNAL_SERVER_ERROR" in response.body


def _run_handler(error: Exception):
    import asyncio

    return asyncio.run(unhandled_exception_handler(_request(), error))
