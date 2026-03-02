"""Pytest fixtures for proxy-based functional tests.

These tests require docker-compose to be running:
    docker-compose up -d

This starts both PostgreSQL and the proxy service.
"""

import asyncio
import os

import psycopg
import pytest
import pytest_asyncio

# PostgreSQL connection parameters (direct connection for setup)
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = "pygwire_test"
POSTGRES_USER = "postgres"
POSTGRES_PASSWORD = "testpass"

# Proxy configuration (assumes docker-compose proxy on port 5433)
PROXY_HOST = "localhost"
PROXY_PORT = 5433


async def _wait_for_proxy(timeout: float = 10.0):
    """Wait for docker-compose proxy to be ready.

    This is a regular async function (not a fixture) so it can be called
    from other fixtures to wait for proxy restart after crashes.
    """
    start_time = asyncio.get_event_loop().time()

    while True:
        try:
            # Try to connect to proxy
            _, writer = await asyncio.open_connection(PROXY_HOST, PROXY_PORT)
            writer.close()
            await writer.wait_closed()
            return  # Success!
        except (ConnectionRefusedError, OSError):
            pass

        # Check timeout
        if asyncio.get_event_loop().time() - start_time > timeout:
            pytest.fail(
                f"Proxy not available on {PROXY_HOST}:{PROXY_PORT} after {timeout}s. "
                "Did you run 'docker-compose up -d'?"
            )

        await asyncio.sleep(0.2)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def wait_for_proxy():
    """Wait for docker-compose proxy to be ready before any tests run.

    This fixture runs automatically before any tests.
    Assumes docker-compose is already running (docker-compose up -d).
    """
    await _wait_for_proxy()


@pytest_asyncio.fixture(scope="session")
async def db_setup():
    """Setup test database schema and initial data once per session."""
    # Connect as superuser to setup (directly to PostgreSQL, not through proxy)
    conn = await psycopg.AsyncConnection.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )

    try:
        # Clean tables before test session
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE test_schema.simple_table, test_schema.copy_test")
            # Insert initial data
            await cur.execute(
                """INSERT INTO test_schema.simple_table (name, value) VALUES
                ('Alice', 100), ('Bob', 200), ('Charlie', 300)"""
            )
        await conn.commit()

        yield

    finally:
        await conn.close()


@pytest_asyncio.fixture
async def db_connection(db_setup):
    """psycopg3 connection through proxy.

    Connects through the docker-compose proxy (port 5433) which runs in --strict mode.
    If the proxy crashes due to a state machine error, the connection will fail.

    Success = connection works and queries succeed
    Failure = connection error or proxy crash (state machine error)
    """
    # Wait for proxy to be ready (may have restarted after previous test crash)
    await _wait_for_proxy()

    # Connect through proxy (port 5433)
    conn = await psycopg.AsyncConnection.connect(
        host=PROXY_HOST,
        port=PROXY_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )

    try:
        # Clean up test data before test
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE test_schema.simple_table, test_schema.copy_test")
            await cur.execute(
                """INSERT INTO test_schema.simple_table (name, value) VALUES
                ('Alice', 100), ('Bob', 200), ('Charlie', 300)"""
            )
        await conn.commit()

        yield conn

    finally:
        try:
            await conn.close()
        except Exception:
            pass


# Pytest configuration
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "proxy_functional: proxy-based functional tests")
    config.addinivalue_line("markers", "simple_query: simple query protocol tests")
    config.addinivalue_line("markers", "extended_query: extended query protocol tests")
    config.addinivalue_line("markers", "copy: COPY protocol tests")
    config.addinivalue_line("markers", "transactions: transaction tests")
    config.addinivalue_line("markers", "auth: authentication tests")
    config.addinivalue_line("markers", "notifications: LISTEN/NOTIFY tests")
