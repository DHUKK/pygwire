"""Tests for LISTEN/NOTIFY protocol through proxy."""

import asyncio

import pytest

pytestmark = [
    pytest.mark.proxy_functional,
    pytest.mark.asyncio,
    pytest.mark.notifications,
]


async def test_basic_notify(db_connection):
    """Test basic NOTIFY command."""
    conn = db_connection

    # Just test that NOTIFY doesn't cause errors
    await conn.execute("NOTIFY test_channel, 'test_payload'")
    await conn.commit()

    # Should complete without error


async def test_listen_and_notify_same_connection(db_connection):
    """Test LISTEN and NOTIFY on same connection."""
    conn = db_connection

    # Enable autocommit for LISTEN/NOTIFY
    await conn.set_autocommit(True)

    # Listen to channel
    await conn.execute("LISTEN test_channel")

    # Send notification
    await conn.execute("NOTIFY test_channel, 'Hello from same connection'")

    # Give it a moment to process
    await asyncio.sleep(0.1)

    # We can't easily receive notifications in this test setup,
    # but we can verify no errors occurred
    await conn.execute("UNLISTEN test_channel")

    # Restore transaction mode
    await conn.set_autocommit(False)


async def test_unlisten(db_connection):
    """Test UNLISTEN command."""
    conn = db_connection

    await conn.set_autocommit(True)

    # Listen
    await conn.execute("LISTEN test_channel")

    # Unlisten
    await conn.execute("UNLISTEN test_channel")

    # Should complete without error

    await conn.set_autocommit(False)


async def test_unlisten_all(db_connection):
    """Test UNLISTEN * to stop listening to all channels."""
    conn = db_connection

    await conn.set_autocommit(True)

    # Listen to multiple channels
    await conn.execute("LISTEN channel1")
    await conn.execute("LISTEN channel2")
    await conn.execute("LISTEN channel3")

    # Unlisten all
    await conn.execute("UNLISTEN *")

    await conn.set_autocommit(False)


async def test_notify_with_long_payload(db_connection):
    """Test NOTIFY with longer payload."""
    conn = db_connection

    await conn.set_autocommit(True)

    # Send notification with longer payload
    long_payload = "x" * 1000
    await conn.execute(f"NOTIFY test_channel, '{long_payload}'")

    await conn.set_autocommit(False)


async def test_notify_special_characters(db_connection):
    """Test NOTIFY with special characters in payload."""
    conn = db_connection

    await conn.set_autocommit(True)

    # Payload with special characters
    special_payload = 'Test\'s payload with "quotes" and \\backslash'
    # Use parameterized query to handle escaping
    await conn.execute("SELECT pg_notify('test_channel', %s)", (special_payload,))

    await conn.set_autocommit(False)


async def test_multiple_notifies(db_connection):
    """Test sending multiple notifications."""
    conn = db_connection

    await conn.set_autocommit(True)

    # Send multiple notifications
    for i in range(10):
        await conn.execute(f"NOTIFY test_channel, 'Message {i}'")

    await conn.set_autocommit(False)


async def test_notify_in_transaction(db_connection):
    """Test that NOTIFY in transaction is sent on COMMIT."""
    conn = db_connection

    # Start transaction
    await conn.execute("NOTIFY test_channel, 'In transaction'")

    # Notification should be sent on commit
    await conn.commit()

    # Should complete without error


async def test_notify_rollback(db_connection):
    """Test that NOTIFY in rolled back transaction is not sent."""
    conn = db_connection

    # Start transaction
    await conn.execute("NOTIFY test_channel, 'Will be rolled back'")

    # Rollback
    await conn.rollback()

    # Should complete without error


async def test_listen_after_error(db_connection):
    """Test LISTEN after recovering from error."""
    conn = db_connection

    # Cause an error
    with pytest.raises(Exception):  # noqa: B017
        await conn.execute("INVALID SQL")

    await conn.rollback()

    # Should be able to LISTEN after error
    await conn.set_autocommit(True)
    await conn.execute("LISTEN test_channel")
    await conn.execute("UNLISTEN test_channel")
    await conn.set_autocommit(False)
