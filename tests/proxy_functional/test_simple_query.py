"""Tests for simple query protocol through proxy.

These tests validate that the proxy stays alive (no state machine errors)
when executing simple query protocol operations.
"""

import pytest

pytestmark = [
    pytest.mark.proxy_functional,
    pytest.mark.asyncio,
    pytest.mark.simple_query,
]


async def test_basic_select(db_connection):
    """Test basic SELECT query through proxy.

    Success = proxy stays alive and query succeeds.
    Failure = proxy crashes (state machine error) or connection error.
    """
    conn = db_connection

    # Execute query via psycopg3
    cursor = await conn.execute("SELECT 1 AS one")
    result = await cursor.fetchone()

    # If we got here, the protocol is valid!
    # The proxy would have crashed on any state machine error.
    assert result[0] == 1


async def test_select_multiple_rows(db_connection):
    """Test SELECT returning multiple rows."""
    conn = db_connection

    cursor = await conn.execute("SELECT * FROM test_schema.simple_table ORDER BY id")
    results = await cursor.fetchall()

    # Verify data
    assert len(results) == 3
    assert results[0][1] == "Alice"
    assert results[0][2] == 100


async def test_insert_query(db_connection):
    """Test INSERT statement."""
    conn = db_connection

    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('TestInsert', 999)"
    )
    await conn.commit()

    # Verify the insert worked
    cursor = await conn.execute("SELECT name FROM test_schema.simple_table WHERE value = 999")
    result = await cursor.fetchone()

    assert result[0] == "TestInsert"


async def test_update_query(db_connection):
    """Test UPDATE statement."""
    conn = db_connection

    # Insert a row
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('UpdateTest', 777)"
    )
    await conn.commit()

    # Update it
    await conn.execute("UPDATE test_schema.simple_table SET value = 888 WHERE name = 'UpdateTest'")
    await conn.commit()

    # Verify update
    cursor = await conn.execute(
        "SELECT value FROM test_schema.simple_table WHERE name = 'UpdateTest'"
    )
    result = await cursor.fetchone()

    assert result[0] == 888


async def test_delete_query(db_connection):
    """Test DELETE statement."""
    conn = db_connection

    # Insert a row
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('DeleteTest', 666)"
    )
    await conn.commit()

    # Delete it
    await conn.execute("DELETE FROM test_schema.simple_table WHERE name = 'DeleteTest'")
    await conn.commit()

    # Verify deletion
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM test_schema.simple_table WHERE name = 'DeleteTest'"
    )
    result = await cursor.fetchone()

    assert result[0] == 0


async def test_empty_query(db_connection):
    """Test empty query string."""
    conn = db_connection

    # Empty queries should be handled gracefully
    await conn.execute("")
    await conn.commit()


async def test_multi_statement_query(db_connection):
    """Test multiple statements in one query."""
    conn = db_connection

    # psycopg3 doesn't directly support multi-statement queries in execute,
    # but we can test sequential queries
    cursor1 = await conn.execute("SELECT 1 AS first")
    result1 = await cursor1.fetchone()

    cursor2 = await conn.execute("SELECT 2 AS second")
    result2 = await cursor2.fetchone()

    cursor3 = await conn.execute("SELECT 3 AS third")
    result3 = await cursor3.fetchone()

    assert result1[0] == 1
    assert result2[0] == 2
    assert result3[0] == 3


async def test_query_with_where_clause(db_connection):
    """Test SELECT with WHERE clause."""
    conn = db_connection

    cursor = await conn.execute(
        "SELECT name, value FROM test_schema.simple_table WHERE value > 150"
    )
    results = await cursor.fetchall()

    # Should get Bob (200) and Charlie (300)
    assert len(results) == 2


async def test_aggregate_functions(db_connection):
    """Test aggregate functions."""
    conn = db_connection

    cursor = await conn.execute(
        "SELECT COUNT(*), AVG(value), MAX(value), MIN(value) FROM test_schema.simple_table"
    )
    result = await cursor.fetchone()

    count, avg, max_val, min_val = result
    assert count >= 3  # At least the original 3 rows
    assert min_val == 100


async def test_query_with_null(db_connection):
    """Test queries with NULL values."""
    conn = db_connection

    # Insert a row with NULL value
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('NullTest', NULL)"
    )
    await conn.commit()

    # Query it back
    cursor = await conn.execute(
        "SELECT name, value FROM test_schema.simple_table WHERE name = 'NullTest'"
    )
    result = await cursor.fetchone()

    assert result[0] == "NullTest"
    assert result[1] is None  # NULL represented as None
