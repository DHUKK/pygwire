"""Tests for transaction control through proxy."""

import pytest

pytestmark = [
    pytest.mark.proxy_functional,
    pytest.mark.asyncio,
    pytest.mark.transactions,
]


async def test_basic_commit(db_connection):
    """Test basic transaction with COMMIT."""
    conn = db_connection

    # Insert in transaction
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('CommitTest', 4001)"
    )
    await conn.commit()

    # Verify it was committed
    cursor = await conn.execute(
        "SELECT value FROM test_schema.simple_table WHERE name = 'CommitTest'"
    )
    result = await cursor.fetchone()

    assert result[0] == 4001


async def test_basic_rollback(db_connection):
    """Test transaction with ROLLBACK."""
    conn = db_connection

    # Insert in transaction
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('RollbackTest', 4002)"
    )

    # Rollback
    await conn.rollback()

    # Verify it was rolled back
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM test_schema.simple_table WHERE name = 'RollbackTest'"
    )
    result = await cursor.fetchone()

    assert result[0] == 0


async def test_multiple_operations_commit(db_connection):
    """Test multiple operations in single transaction."""
    conn = db_connection

    # Multiple inserts
    await conn.execute("INSERT INTO test_schema.simple_table (name, value) VALUES ('Multi1', 4003)")
    await conn.execute("INSERT INTO test_schema.simple_table (name, value) VALUES ('Multi2', 4004)")
    await conn.execute("UPDATE test_schema.simple_table SET value = 4005 WHERE name = 'Multi1'")

    await conn.commit()

    # Verify
    cursor = await conn.execute("SELECT value FROM test_schema.simple_table WHERE name = 'Multi1'")
    result = await cursor.fetchone()

    assert result[0] == 4005


async def test_multiple_operations_rollback(db_connection):
    """Test rolling back multiple operations."""
    conn = db_connection

    # Multiple operations
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('RbMulti1', 4006)"
    )
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('RbMulti2', 4007)"
    )

    await conn.rollback()

    # Verify nothing was committed
    cursor = await conn.execute("SELECT COUNT(*) FROM test_schema.simple_table WHERE value >= 4006")
    result = await cursor.fetchone()

    assert result[0] == 0


async def test_savepoint(db_connection):
    """Test SAVEPOINT functionality."""
    conn = db_connection

    # Start transaction
    await conn.execute("INSERT INTO test_schema.simple_table (name, value) VALUES ('SP1', 4010)")

    # Create savepoint
    await conn.execute("SAVEPOINT sp1")

    # More operations
    await conn.execute("INSERT INTO test_schema.simple_table (name, value) VALUES ('SP2', 4011)")

    # Rollback to savepoint
    await conn.execute("ROLLBACK TO SAVEPOINT sp1")

    await conn.commit()

    # Verify: SP1 should exist, SP2 should not
    cursor = await conn.execute("SELECT COUNT(*) FROM test_schema.simple_table WHERE name = 'SP1'")
    result1 = await cursor.fetchone()

    cursor = await conn.execute("SELECT COUNT(*) FROM test_schema.simple_table WHERE name = 'SP2'")
    result2 = await cursor.fetchone()

    assert result1[0] == 1
    assert result2[0] == 0


async def test_nested_savepoints(db_connection):
    """Test nested savepoints."""
    conn = db_connection

    await conn.execute("INSERT INTO test_schema.simple_table (name, value) VALUES ('Nest1', 4020)")
    await conn.execute("SAVEPOINT sp1")

    await conn.execute("INSERT INTO test_schema.simple_table (name, value) VALUES ('Nest2', 4021)")
    await conn.execute("SAVEPOINT sp2")

    await conn.execute("INSERT INTO test_schema.simple_table (name, value) VALUES ('Nest3', 4022)")

    # Rollback to sp2
    await conn.execute("ROLLBACK TO SAVEPOINT sp2")

    await conn.commit()

    # Verify: Nest1 and Nest2 exist, Nest3 doesn't
    cursor = await conn.execute(
        "SELECT name FROM test_schema.simple_table WHERE value >= 4020 ORDER BY value"
    )
    results = await cursor.fetchall()

    names = [r[0] for r in results]
    assert names == ["Nest1", "Nest2"]


async def test_release_savepoint(db_connection):
    """Test RELEASE SAVEPOINT."""
    conn = db_connection

    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('Release1', 4030)"
    )
    await conn.execute("SAVEPOINT sp1")

    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('Release2', 4031)"
    )

    # Release savepoint (commit the savepoint's changes)
    await conn.execute("RELEASE SAVEPOINT sp1")

    await conn.commit()

    # Both should exist
    cursor = await conn.execute("SELECT COUNT(*) FROM test_schema.simple_table WHERE value >= 4030")
    result = await cursor.fetchone()

    assert result[0] == 2


async def test_autocommit_mode(db_connection):
    """Test that autocommit mode works."""
    conn = db_connection

    # Enable autocommit
    await conn.set_autocommit(True)

    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('AutoCommit', 4040)"
    )

    # Disable autocommit for cleanup
    await conn.set_autocommit(False)

    # Verify it was committed immediately
    cursor = await conn.execute(
        "SELECT value FROM test_schema.simple_table WHERE name = 'AutoCommit'"
    )
    result = await cursor.fetchone()

    assert result[0] == 4040


async def test_transaction_isolation_read_committed(db_connection):
    """Test READ COMMITTED isolation level."""
    conn = db_connection

    # Set isolation level
    await conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")

    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('IsoRead', 4050)"
    )
    await conn.commit()

    cursor = await conn.execute("SELECT value FROM test_schema.simple_table WHERE name = 'IsoRead'")
    result = await cursor.fetchone()

    assert result[0] == 4050


async def test_transaction_with_error_recovery(db_connection):
    """Test that transaction can continue after an error."""
    conn = db_connection

    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('ErrorTrans1', 4060)"
    )

    # This will cause an error (syntax error)
    try:
        await conn.execute("SELECT * FROM nonexistent_table")
    except Exception:
        pass  # Expected

    # Roll back the failed transaction
    await conn.rollback()

    # Start new transaction
    await conn.execute(
        "INSERT INTO test_schema.simple_table (name, value) VALUES ('ErrorTrans2', 4061)"
    )
    await conn.commit()

    # Verify second insert worked
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM test_schema.simple_table WHERE name = 'ErrorTrans2'"
    )
    result = await cursor.fetchone()

    assert result[0] == 1
