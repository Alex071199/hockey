"""SQLite dialect backed by the async Hrana v2 HTTP driver (Turso cloud).

Follows the same adapter pattern as SQLAlchemy's aiosqlite dialect:
sync-facing adapter objects that bridge to the async driver via await_only.
"""

from collections import deque
from types import ModuleType
from typing import Any, Optional

from sqlalchemy import pool
from sqlalchemy.connectors.asyncio import AsyncAdapt_dbapi_module
from sqlalchemy.dialects.sqlite.base import SQLiteExecutionContext
from sqlalchemy.dialects.sqlite.pysqlite import SQLiteDialect_pysqlite
from sqlalchemy.engine import AdaptedConnection
from sqlalchemy.util.concurrency import await_only


class AsyncAdapt_hrana_cursor:
    __slots__ = (
        "_adapt_connection",
        "_connection",
        "description",
        "await_",
        "_rows",
        "arraysize",
        "rowcount",
        "lastrowid",
    )

    server_side = False

    def __init__(self, adapt_connection: "AsyncAdapt_hrana_connection"):
        self._adapt_connection = adapt_connection
        self._connection = adapt_connection._connection
        self.await_ = adapt_connection.await_
        self.arraysize = 1
        self.rowcount = -1
        self.description = None
        self._rows: deque = deque()

    async def _async_soft_close(self) -> None:
        return

    def close(self) -> None:
        self._rows.clear()

    def execute(self, operation: Any, parameters: Any = None) -> Any:
        try:
            _cursor = self.await_(self._connection.cursor())
            if parameters is None:
                self.await_(_cursor.execute(operation))
            else:
                self.await_(_cursor.execute(operation, parameters))

            if _cursor.description:
                self.description = _cursor.description
                self.lastrowid = self.rowcount = -1
                self._rows = deque(self.await_(_cursor.fetchall()))
            else:
                self.description = None
                self.lastrowid = _cursor.lastrowid
                self.rowcount = _cursor.rowcount

            self.await_(_cursor.close())
        except Exception as error:
            self._adapt_connection._handle_exception(error)

    def executemany(self, operation: Any, seq_of_parameters: Any) -> Any:
        try:
            _cursor = self.await_(self._connection.cursor())
            self.await_(_cursor.executemany(operation, seq_of_parameters))
            self.description = None
            self.lastrowid = _cursor.lastrowid
            self.rowcount = _cursor.rowcount
            self.await_(_cursor.close())
        except Exception as error:
            self._adapt_connection._handle_exception(error)

    def setinputsizes(self, *inputsizes: Any) -> None:
        pass

    def __iter__(self):
        while self._rows:
            yield self._rows.popleft()

    def fetchone(self) -> Optional[Any]:
        if self._rows:
            return self._rows.popleft()
        return None

    def fetchmany(self, size: Optional[int] = None):
        if size is None:
            size = self.arraysize
        rr = self._rows
        return [rr.popleft() for _ in range(min(size, len(rr)))]

    def fetchall(self):
        retval = list(self._rows)
        self._rows.clear()
        return retval


class AsyncAdapt_hrana_connection(AdaptedConnection):
    await_ = staticmethod(await_only)
    __slots__ = ("dbapi",)

    def __init__(self, dbapi: Any, connection: Any):
        self.dbapi = dbapi
        self._connection = connection

    def cursor(self, server_side: bool = False) -> AsyncAdapt_hrana_cursor:
        return AsyncAdapt_hrana_cursor(self)

    def execute(self, *args: Any, **kw: Any) -> Any:
        return self.await_(self._connection.execute(*args, **kw))

    def rollback(self) -> None:
        try:
            self.await_(self._connection.rollback())
        except Exception as error:
            self._handle_exception(error)

    def commit(self) -> None:
        try:
            self.await_(self._connection.commit())
        except Exception as error:
            self._handle_exception(error)

    def close(self) -> None:
        try:
            self.await_(self._connection.close())
        except Exception as error:
            self._handle_exception(error)

    def _handle_exception(self, error: Exception) -> Any:
        raise error


class AsyncAdapt_hrana_dbapi(AsyncAdapt_dbapi_module):
    def __init__(self, hrana: ModuleType):
        self.hrana = hrana
        self.paramstyle = "qmark"
        self._init_dbapi_attributes()

    def _init_dbapi_attributes(self) -> None:
        for name in (
            "DatabaseError",
            "Error",
            "IntegrityError",
            "NotSupportedError",
            "OperationalError",
            "ProgrammingError",
            "sqlite_version",
            "sqlite_version_info",
        ):
            setattr(self, name, getattr(self.hrana, name))

    def connect(self, *arg: Any, **kw: Any) -> AsyncAdapt_hrana_connection:
        connection = self.hrana.connect(*arg, **kw)
        return AsyncAdapt_hrana_connection(self, connection)


class SQLiteExecutionContext_hrana(SQLiteExecutionContext):
    pass


class SQLiteDialect_hrana(SQLiteDialect_pysqlite):
    name = "sqlite"
    driver = "hrana"
    is_async = True
    has_terminate = False
    supports_statement_cache = True

    execution_ctx_cls = SQLiteExecutionContext_hrana

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.server_version_info = (3, 46, 1)

    @classmethod
    def import_dbapi(cls) -> AsyncAdapt_hrana_dbapi:
        from app import hrana_dbapi

        return AsyncAdapt_hrana_dbapi(hrana_dbapi)

    @classmethod
    def get_pool_class(cls, url) -> type[pool.Pool]:
        return pool.AsyncAdaptedQueuePool

    def create_connect_args(self, url):
        host = url.host or ""
        if url.database:
            host = f"{host}/{url.database}" if host else url.database
        return ([host], {})

    def on_connect(self):
        def connect(conn):
            return conn

        return connect

    def initialize(self, connection) -> None:
        pass

    def get_isolation_level(self, dbapi_connection) -> str:
        return "SERIALIZABLE"

    def get_default_isolation_level(self, dbapi_connection) -> str:
        return "SERIALIZABLE"


dialect = SQLiteDialect_hrana
