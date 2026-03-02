"""Tests for error handling and recovery through proxy."""

import psycopg
import pytest

pytestmark = [pytest.mark.proxy_functional, pytest.mark.asyncio]


async def test_syntax_error_recovery(db_connection):
    """Test recovery from syntax error."""
    conn = db_connection

    # Execute invalid SQL
    with pytest.raises(psycopg.errors.SyntaxError):
        await conn.execute("SELEC * FROM test_schema.simple_table")  # Typo: SELEC

    await conn.rollback()

    # Should be able to execute valid query after error
    cursor = await conn.execute("SELECT 1")
    result = await cursor.fetchone()

    assert result[0] == 1


async def test_undefined_table_error(db_connection):
    """Test recovery from undefined table error."""
    conn = db_connection

    with pytest.raises(psycopg.errors.UndefinedTable):
        await conn.execute("SELECT * FROM nonexistent_table")

    await conn.rollback()

    # Should be able to continue
    cursor = await conn.execute("SELECT 1")
    result = await cursor.fetchone()

    assert result[0] == 1


async def test_division_by_zero_error(db_connection):
    """Test recovery from runtime error."""
    conn = db_connection

    with pytest.raises(psycopg.errors.DivisionByZero):
        await conn.execute("SELECT 1 / 0")

    await conn.rollback()

    # Should be able to continue
    cursor = await conn.execute("SELECT 2 / 1")
    result = await cursor.fetchone()

    assert result[0] == 2


async def test_unique_violation_error(db_connection):
    """Test recovery from constraint violation."""
    conn = db_connection

    # First insert should succeed
    await conn.execute(
        "INSERT INTO test_schema.simple_table (id, name, value) VALUES (99999, 'Unique1', 5000)"
    )
    await conn.commit()

    # Second insert with same ID should fail
    with pytest.raises(psycopg.errors.UniqueViolation):
        await conn.execute(
            "INSERT INTO test_schema.simple_table (id, name, value) VALUES (99999, 'Unique2', 5001)"
        )

    await conn.rollback()

    # Should be able to continue
    cursor = await conn.execute("SELECT 1")
    result = await cursor.fetchone()

    assert result[0] == 1


async def test_not_null_violation_error(db_connection):
    """Test recovery from NOT NULL constraint violation."""
    conn = db_connection

    with pytest.raises(psycopg.errors.NotNullViolation):
        await conn.execute("INSERT INTO test_schema.simple_table (name) VALUES (NULL)")

    await conn.rollback()

    # Should be able to continue
    cursor = await conn.execute("SELECT 1")
    result = await cursor.fetchone()

    assert result[0] == 1


async def test_type_mismatch_error(db_connection):
    """Test recovery from type mismatch error."""
    conn = db_connection

    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        await conn.execute("SELECT * FROM test_schema.simple_table WHERE value = 'not_a_number'")

    await conn.rollback()

    # Should be able to continue
    cursor = await conn.execute("SELECT 1")
    result = await cursor.fetchone()

    assert result[0] == 1


async def test_multiple_errors_in_sequence(db_connection):
    """Test handling multiple errors in sequence."""
    conn = db_connection

    # First error
    with pytest.raises(psycopg.errors.SyntaxError):
        await conn.execute("INVALID SQL")

    await conn.rollback()

    # Second error
    with pytest.raises(psycopg.errors.UndefinedTable):
        await conn.execute("SELECT * FROM nonexistent")

    await conn.rollback()

    # Third error
    with pytest.raises(psycopg.errors.DivisionByZero):
        await conn.execute("SELECT 1 / 0")

    await conn.rollback()

    # Should still be able to execute valid query
    cursor = await conn.execute("SELECT 1")
    result = await cursor.fetchone()

    assert result[0] == 1


async def test_error_in_transaction_blocks_further_commands(db_connection):
    """Test that error in transaction blocks further commands until rollback."""
    conn = db_connection

    # Start transaction
    await conn.execute("INSERT INTO test_schema.simple_table (name, value) VALUES ('Trans1', 5100)")

    # Cause error
    with pytest.raises(psycopg.errors.SyntaxError):
        await conn.execute("INVALID SQL")

    # Further commands should fail (transaction is in error state)
    with pytest.raises(psycopg.errors.InFailedSqlTransaction):
        await conn.execute("SELECT 1")

    # Rollback should fix it
    await conn.rollback()

    # Now should work
    cursor = await conn.execute("SELECT 1")
    result = await cursor.fetchone()

    assert result[0] == 1


async def test_successful_operations_after_error(db_connection):
    """Test that operations after error recovery work normally."""
    conn = db_connection

    # Error
    with pytest.raises(psycopg.errors.SyntaxError):
        await conn.execute("INVALID")

    await conn.rollback()

    # Multiple successful operations
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('AfterError1', 5200)"
    )
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('AfterError2', 5201)"
    )
    await conn.execute(
        "UPDATE test_schema.simple_table SET value = 5202 WHERE name = 'AfterError1'"
    )
    await conn.commit()

    # Verify
    cursor = await conn.execute("SELECT COUNT(*) FROM test_schema.simple_table WHERE value >= 5200")
    result = await cursor.fetchone()

    assert result[0] == 2


async def test_parameterized_query_error(db_connection):
    """Test error recovery with parameterized queries."""
    conn = db_connection

    # Error with parameter
    with pytest.raises(psycopg.errors.UndefinedTable):
        await conn.execute("SELECT * FROM nonexistent WHERE id = %s", (1,))

    await conn.rollback()

    # Successful parameterized query
    cursor = await conn.execute(
        "SELECT name FROM test_schema.simple_table WHERE value = %s", (100,)
    )
    result = await cursor.fetchone()

    assert result[0] == "Alice"
