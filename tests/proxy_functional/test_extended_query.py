"""Tests for extended query protocol through proxy.

The extended query protocol uses Parse/Bind/Execute/Sync messages
and supports pipelining (multiple queries before waiting for responses).
"""

import pytest

pytestmark = [
    pytest.mark.proxy_functional,
    pytest.mark.asyncio,
    pytest.mark.extended_query,
]


async def test_basic_parameterized_query(db_connection):
    """Test basic parameterized query using extended protocol."""
    conn = db_connection

    # psycopg3 uses extended protocol by default with %s placeholders
    cursor = await conn.execute(
        "SELECT name FROM test_schema.simple_table WHERE value = %s", (100,)
    )
    result = await cursor.fetchone()

    assert result[0] == "Alice"


async def test_multiple_parameters(db_connection):
    """Test query with multiple parameters."""
    conn = db_connection

    cursor = await conn.execute(
        "SELECT name FROM test_schema.simple_table WHERE value > %s AND value < %s",
        (150, 250),
    )
    result = await cursor.fetchone()

    assert result[0] == "Bob"


async def test_prepared_statement_reuse(db_connection):
    """Test preparing and reusing a statement."""
    conn = db_connection

    # Prepare statement
    async with conn.cursor() as cur:
        await cur.execute("SELECT name FROM test_schema.simple_table WHERE value = %s", (100,))
        result1 = await cur.fetchone()

        # Reuse with different parameter
        await cur.execute("SELECT name FROM test_schema.simple_table WHERE value = %s", (200,))
        result2 = await cur.fetchone()

    assert result1[0] == "Alice"
    assert result2[0] == "Bob"


async def test_insert_with_returning(db_connection):
    """Test INSERT with RETURNING clause."""
    conn = db_connection

    cursor = await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES (%s, %s) RETURNING id, name",
        ("NewRow", 999),
    )
    result = await cursor.fetchone()

    assert result[1] == "NewRow"


async def test_batch_insert(db_connection):
    """Test batch insert with multiple rows."""
    conn = db_connection

    # Insert multiple rows
    data = [
        ("Batch1", 1001),
        ("Batch2", 1002),
        ("Batch3", 1003),
    ]

    async with conn.cursor() as cur:
        for name, value in data:
            await cur.execute(
                "INSERT INTO test_schema.simple_table (name, value) VALUES (%s, %s)",
                (name, value),
            )

    await conn.commit()

    # Verify
    cursor = await conn.execute("SELECT COUNT(*) FROM test_schema.simple_table WHERE value >= 1001")
    result = await cursor.fetchone()
    assert result[0] == 3


async def test_null_parameter(db_connection):
    """Test NULL as parameter."""
    conn = db_connection

    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES (%s, %s)",
        ("NullValue", None),
    )
    await conn.commit()

    cursor = await conn.execute("SELECT name FROM test_schema.simple_table WHERE value IS NULL")
    result = await cursor.fetchone()

    assert result[0] == "NullValue"


async def test_text_parameter(db_connection):
    """Test text parameter with special characters."""
    conn = db_connection

    special_text = 'Test\'s "quoted" text\\nwith\\ttabs'
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES (%s, %s)",
        (special_text, 5000),
    )
    await conn.commit()

    cursor = await conn.execute(
        "SELECT name FROM test_schema.simple_table WHERE value = %s", (5000,)
    )
    result = await cursor.fetchone()

    assert result[0] == special_text


async def test_large_result_set(db_connection):
    """Test query returning many rows."""
    conn = db_connection

    # Insert 100 rows
    async with conn.cursor() as cur:
        for i in range(100):
            await cur.execute(
                "INSERT INTO test_schema.simple_table (name, value) VALUES (%s, %s)",
                (f"Row{i}", 2000 + i),
            )

    await conn.commit()

    # Fetch all
    cursor = await conn.execute(
        "SELECT name FROM test_schema.simple_table WHERE value >= 2000 ORDER BY value"
    )
    results = await cursor.fetchall()

    assert len(results) == 100
    assert results[0][0] == "Row0"
    assert results[99][0] == "Row99"


async def test_update_with_parameters(db_connection):
    """Test UPDATE with parameters."""
    conn = db_connection

    # Update Alice's value
    cursor = await conn.execute(
        "UPDATE test_schema.simple_table SET value = %s WHERE name = %s", (150, "Alice")
    )
    await conn.commit()

    # Verify
    cursor = await conn.execute(
        "SELECT value FROM test_schema.simple_table WHERE name = %s", ("Alice",)
    )
    result = await cursor.fetchone()

    assert result[0] == 150


async def test_delete_with_parameters(db_connection):
    """Test DELETE with parameters."""
    conn = db_connection

    # Insert test row
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES (%s, %s)",
        ("ToDelete", 9999),
    )
    await conn.commit()

    # Delete it
    await conn.execute("DELETE FROM test_schema.simple_table WHERE name = %s", ("ToDelete",))
    await conn.commit()

    # Verify
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM test_schema.simple_table WHERE name = %s", ("ToDelete",)
    )
    result = await cursor.fetchone()

    assert result[0] == 0


async def test_multiple_statements_in_transaction(db_connection):
    """Test multiple parameterized statements in a transaction."""
    conn = db_connection

    # Multiple operations in transaction
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES (%s, %s)",
        ("Trans1", 3001),
    )
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES (%s, %s)",
        ("Trans2", 3002),
    )
    await conn.execute(
        "UPDATE test_schema.simple_table SET value = %s WHERE name = %s",
        (3003, "Trans1"),
    )
    await conn.commit()

    # Verify
    cursor = await conn.execute(
        "SELECT value FROM test_schema.simple_table WHERE name = %s", ("Trans1",)
    )
    result = await cursor.fetchone()

    assert result[0] == 3003


async def test_query_with_aggregate_and_params(db_connection):
    """Test aggregate query with parameters."""
    conn = db_connection

    cursor = await conn.execute(
        "SELECT COUNT(*), AVG(value) FROM test_schema.simple_table WHERE value > %s",
        (100,),
    )
    result = await cursor.fetchone()

    count, avg = result
    assert count >= 2  # At least Bob and Charlie
