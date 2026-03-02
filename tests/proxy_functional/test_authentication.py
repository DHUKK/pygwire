"""Tests for authentication methods through proxy.

Tests different PostgreSQL authentication methods:
- Trust authentication (no password)
- MD5 password authentication
- SCRAM-SHA-256 authentication
"""

import psycopg
import pytest

pytestmark = [pytest.mark.proxy_functional, pytest.mark.asyncio, pytest.mark.auth]

PROXY_HOST = "localhost"
PROXY_PORT = 5433
POSTGRES_DB = "pygwire_test"


async def test_trust_authentication():
    """Test trust authentication (no password required)."""
    # trust_user is configured with trust auth in pg_hba.conf
    conn = await psycopg.AsyncConnection.connect(
        host=PROXY_HOST,
        port=PROXY_PORT,
        dbname=POSTGRES_DB,
        user="trust_user",
        # No password needed for trust auth
    )

    try:
        # Should be able to query
        cursor = await conn.execute("SELECT current_user")
        result = await cursor.fetchone()
        assert result[0] == "trust_user"
    finally:
        await conn.close()


async def test_md5_authentication():
    """Test MD5 password authentication."""
    # md5_user is configured with md5 auth in pg_hba.conf
    conn = await psycopg.AsyncConnection.connect(
        host=PROXY_HOST,
        port=PROXY_PORT,
        dbname=POSTGRES_DB,
        user="md5_user",
        password="md5pass",
    )

    try:
        # Should be able to query
        cursor = await conn.execute("SELECT current_user")
        result = await cursor.fetchone()
        assert result[0] == "md5_user"
    finally:
        await conn.close()


async def test_md5_authentication_wrong_password():
    """Test MD5 authentication fails with wrong password."""
    with pytest.raises(psycopg.OperationalError) as exc_info:
        await psycopg.AsyncConnection.connect(
            host=PROXY_HOST,
            port=PROXY_PORT,
            dbname=POSTGRES_DB,
            user="md5_user",
            password="wrongpass",
        )

    # Should get authentication error
    assert (
        "authentication" in str(exc_info.value).lower() or "password" in str(exc_info.value).lower()
    )


async def test_scram_sha256_authentication():
    """Test SCRAM-SHA-256 authentication."""
    # scram_user is configured with scram-sha-256 auth in pg_hba.conf
    conn = await psycopg.AsyncConnection.connect(
        host=PROXY_HOST,
        port=PROXY_PORT,
        dbname=POSTGRES_DB,
        user="scram_user",
        password="scrampass",
    )

    try:
        # Should be able to query
        cursor = await conn.execute("SELECT current_user")
        result = await cursor.fetchone()
        assert result[0] == "scram_user"
    finally:
        await conn.close()


async def test_scram_authentication_wrong_password():
    """Test SCRAM authentication fails with wrong password."""
    with pytest.raises(psycopg.OperationalError) as exc_info:
        await psycopg.AsyncConnection.connect(
            host=PROXY_HOST,
            port=PROXY_PORT,
            dbname=POSTGRES_DB,
            user="scram_user",
            password="wrongpass",
        )

    # Should get authentication error
    assert (
        "authentication" in str(exc_info.value).lower() or "password" in str(exc_info.value).lower()
    )


async def test_auth_user_can_query_test_schema():
    """Test that authenticated users can access test_schema."""
    # Test with md5_user
    conn = await psycopg.AsyncConnection.connect(
        host=PROXY_HOST,
        port=PROXY_PORT,
        dbname=POSTGRES_DB,
        user="md5_user",
        password="md5pass",
    )

    try:
        # Should be able to query test_schema
        cursor = await conn.execute("SELECT COUNT(*) FROM test_schema.simple_table")
        result = await cursor.fetchone()
        assert result[0] >= 0  # Just verify we can query
    finally:
        await conn.close()


async def test_auth_user_can_insert():
    """Test that authenticated users can insert data."""
    conn = await psycopg.AsyncConnection.connect(
        host=PROXY_HOST,
        port=PROXY_PORT,
        dbname=POSTGRES_DB,
        user="scram_user",
        password="scrampass",
    )

    try:
        # Should be able to insert
        await conn.execute(
            "INSERT INTO test_schema.simple_table (name, value) VALUES (%s, %s)",
            ("auth_test", 9999),
        )
        await conn.commit()

        # Verify insert
        cursor = await conn.execute(
            "SELECT value FROM test_schema.simple_table WHERE name = %s",
            ("auth_test",),
        )
        result = await cursor.fetchone()
        assert result[0] == 9999
    finally:
        await conn.close()


async def test_multiple_auth_methods_concurrently():
    """Test multiple connections with different auth methods work simultaneously."""
    # Connect with all three users
    trust_conn = await psycopg.AsyncConnection.connect(
        host=PROXY_HOST, port=PROXY_PORT, dbname=POSTGRES_DB, user="trust_user"
    )

    md5_conn = await psycopg.AsyncConnection.connect(
        host=PROXY_HOST,
        port=PROXY_PORT,
        dbname=POSTGRES_DB,
        user="md5_user",
        password="md5pass",
    )

    scram_conn = await psycopg.AsyncConnection.connect(
        host=PROXY_HOST,
        port=PROXY_PORT,
        dbname=POSTGRES_DB,
        user="scram_user",
        password="scrampass",
    )

    try:
        # All should work
        cursor1 = await trust_conn.execute("SELECT current_user")
        cursor2 = await md5_conn.execute("SELECT current_user")
        cursor3 = await scram_conn.execute("SELECT current_user")

        result1 = await cursor1.fetchone()
        result2 = await cursor2.fetchone()
        result3 = await cursor3.fetchone()

        assert result1[0] == "trust_user"
        assert result2[0] == "md5_user"
        assert result3[0] == "scram_user"
    finally:
        await trust_conn.close()
        await md5_conn.close()
        await scram_conn.close()
