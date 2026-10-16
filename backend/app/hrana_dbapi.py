"""Minimal async DB-API 2.0 driver for Turso/libSQL over Hrana v2 HTTP.

Pure Python (httpx.AsyncClient), no native extensions. Async methods
match the expectations of SQLAlchemy's asyncio extension (aiosqlite-style).
Interactive transactions are supported via baton (BEGIN/COMMIT/ROLLBACK).
"""

import base64

import httpx

apilevel = "2.0"
threadsafety = 1
paramstyle = "qmark"

sqlite_version = "3.46.1"
sqlite_version_info = (3, 46, 1)


class Error(Exception):
    pass


class Warning(Exception):
    pass


class InterfaceError(Error):
    pass


class DatabaseError(Error):
    pass


class DataError(DatabaseError):
    pass


class OperationalError(DatabaseError):
    pass


class IntegrityError(DatabaseError):
    pass


class InternalError(DatabaseError):
    pass


class ProgrammingError(DatabaseError):
    pass


class NotSupportedError(DatabaseError):
    pass


def _decode_value(cell):
    if cell is None:
        return None
    t = cell.get("type")
    v = cell.get("value")
    if t == "null" or t is None:
        return None
    if t == "integer":
        return int(v)
    if t == "float":
        return float(v)
    if t == "text":
        return v
    if t == "blob":
        return base64.b64decode(v)
    return v


def _encode_value(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": "1" if v else "0"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": repr(v)}
    if isinstance(v, (bytes, bytearray)):
        return {"type": "blob", "value": base64.b64encode(bytes(v)).decode("ascii")}
    return {"type": "text", "value": str(v)}


class Connection:
    def __init__(self, database, auth_token=None, secure=True, timeout=30.0, **_):
        scheme = "https" if secure else "http"
        host = "".join((database or "").split())
        for prefix in ("https://", "http://", "libsql://"):
            if host.startswith(prefix):
                host = host[len(prefix):]
        self._endpoint = f"{scheme}://{host.rstrip('/')}/v2/pipeline"
        self._token = (auth_token or "").strip()
        self._client = httpx.AsyncClient(timeout=timeout)
        self._baton = None
        self._in_tx = False
        self.closed = False

    async def _post(self, requests):
        if self.closed:
            raise InterfaceError("connection is closed")
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        body: dict = {"requests": requests}
        if self._baton:
            body["baton"] = self._baton
        try:
            resp = await self._client.post(self._endpoint, headers=headers, json=body)
        except httpx.HTTPError as e:
            raise OperationalError(f"hrana transport error: {e}") from e
        if resp.status_code >= 400:
            raise OperationalError(
                f"hrana http {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        self._baton = data.get("baton")
        return data.get("results", [])

    async def cursor(self):
        return Cursor(self)

    async def commit(self):
        if self._in_tx:
            results = await self._post([{"type": "commit"}])
            self._in_tx = False
            _raise_on_error(results, "COMMIT")

    async def rollback(self):
        if self._in_tx:
            results = await self._post([{"type": "rollback"}])
            self._in_tx = False
            _raise_on_error(results, "ROLLBACK")

    async def close(self):
        if not self.closed:
            await self._client.aclose()
            self.closed = True
            self._baton = None
            self._in_tx = False


def _raise_on_error(results, context):
    for res in results:
        if res.get("type") == "error":
            err = res.get("error") or {}
            msg = err.get("message") or str(err)
            raise OperationalError(f"{context}: {msg}")


class Cursor:
    arraysize = 1

    def __init__(self, connection):
        self.connection = connection
        self._rows = []
        self._pos = 0
        self.description = None
        self.rowcount = -1
        self.lastrowid = None

    async def close(self):
        pass

    def _reset(self):
        self._rows = []
        self._pos = 0
        self.description = None
        self.rowcount = -1
        self.lastrowid = None

    async def _run(self, requests):
        results = await self.connection._post(requests)
        _raise_on_error(results, "execute")
        return results

    async def execute(self, sql, parameters=None):
        stripped = (sql or "").strip().upper()
        if stripped == "BEGIN" or stripped.startswith("BEGIN "):
            if not self.connection._in_tx:
                await self._run([{"type": "begin"}])
                self.connection._in_tx = True
            self._reset()
            return self
        if stripped == "COMMIT":
            await self.connection.commit()
            self._reset()
            return self
        if stripped == "ROLLBACK":
            await self.connection.rollback()
            self._reset()
            return self

        stmt: dict = {"sql": sql}
        if parameters:
            stmt["args"] = [_encode_value(p) for p in parameters]
        results = await self._run([{"type": "execute", "stmt": stmt}])
        res = results[0] if results else {"type": "ok"}
        if res.get("type") != "ok":
            self._reset()
            return self
        response = res.get("response") or {}
        if response.get("type") != "execute":
            self._reset()
            return self
        result = response.get("result") or {}
        cols = result.get("cols") or []
        if cols:
            self.description = [
                (c.get("name"), None, None, None, None, None, None) for c in cols
            ]
        else:
            self.description = None
        self._rows = [
            tuple(_decode_value(v) for v in row) for row in result.get("rows") or []
        ]
        self._pos = 0
        self.rowcount = result.get("affected_row_count", -1)
        if self.rowcount is None:
            self.rowcount = -1
        self.lastrowid = result.get("last_insert_rowid")
        return self

    async def executemany(self, sql, seq_of_parameters):
        total = 0
        for params in seq_of_parameters:
            await self.execute(sql, params)
            total += max(self.rowcount or 0, 0)
        self.rowcount = total
        return self

    async def fetchone(self):
        if self._pos >= len(self._rows):
            return None
        row = self._rows[self._pos]
        self._pos += 1
        return row

    async def fetchmany(self, size=None):
        size = size or self.arraysize
        chunk = self._rows[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk

    async def fetchall(self):
        chunk = self._rows[self._pos:]
        self._pos = len(self._rows)
        return chunk


def connect(database, auth_token=None, secure=True, timeout=30.0, **kwargs):
    return Connection(
        database,
        auth_token=auth_token,
        secure=secure,
        timeout=timeout,
        **kwargs,
    )
