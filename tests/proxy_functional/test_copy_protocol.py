"""Tests for COPY protocol through proxy."""

import io

import pytest

pytestmark = [pytest.mark.proxy_functional, pytest.mark.asyncio, pytest.mark.copy]


async def test_copy_from_stdin(db_connection):
    """Test COPY FROM STDIN with text data."""
    conn = db_connection

    # Prepare tab-delimited data (default COPY format)
    tsv_data = io.StringIO(
        "1001\tCopyRow1\t100.50\n1002\tCopyRow2\t200.75\n1003\tCopyRow3\t300.25\n"
    )

    # Copy data
    async with conn.cursor() as cur:
        async with cur.copy("COPY test_schema.copy_test (id, name, amount) FROM STDIN") as copy:
            while True:
                line = tsv_data.readline()
                if not line:
                    break
                await copy.write(line.encode())

    await conn.commit()

    # Verify
    cursor = await conn.execute("SELECT COUNT(*) FROM test_schema.copy_test WHERE id >= 1001")
    result = await cursor.fetchone()

    assert result[0] == 3


async def test_copy_to_stdout(db_connection):
    """Test COPY TO STDOUT."""
    conn = db_connection

    # Insert test data
    await conn.execute(
        "INSERT INTO test_schema.copy_test (id, name, amount) VALUES (2001, 'Export1', 100.00)"
    )
    await conn.execute(
        "INSERT INTO test_schema.copy_test (id, name, amount) VALUES (2002, 'Export2', 200.00)"
    )
    await conn.commit()

    # Copy to stdout (use subquery to filter, WHERE not supported in COPY TO)
    output = io.BytesIO()
    async with (
        conn.cursor() as cur,
        cur.copy("COPY (SELECT * FROM test_schema.copy_test WHERE id >= 2001) TO STDOUT") as copy,
    ):
        async for data in copy:
            output.write(data)

    # Verify output
    output_str = output.getvalue().decode()
    assert "Export1" in output_str
    assert "Export2" in output_str


async def test_copy_with_csv_format(db_connection):
    """Test COPY with CSV format."""
    conn = db_connection

    # CSV data with header
    csv_data = io.StringIO("id,name,amount\n3001,CSVRow1,150.25\n3002,CSVRow2,250.50\n")
    csv_data.readline()  # Skip header

    # Copy with CSV format
    async with (
        conn.cursor() as cur,
        cur.copy(
            "COPY test_schema.copy_test (id, name, amount) FROM STDIN WITH (FORMAT CSV)"
        ) as copy,
    ):
        while True:
            line = csv_data.readline()
            if not line:
                break
            await copy.write(line.encode())

    await conn.commit()

    # Verify
    cursor = await conn.execute("SELECT name FROM test_schema.copy_test WHERE id = 3001")
    result = await cursor.fetchone()

    assert result[0] == "CSVRow1"


async def test_copy_with_delimiter(db_connection):
    """Test COPY with custom delimiter."""
    conn = db_connection

    # Tab-delimited data
    tsv_data = io.StringIO("4001\tTabRow1\t100.00\n4002\tTabRow2\t200.00\n")

    # Copy with tab delimiter
    async with (
        conn.cursor() as cur,
        cur.copy(
            "COPY test_schema.copy_test (id, name, amount) FROM STDIN WITH (DELIMITER E'\\t')"
        ) as copy,
    ):
        while True:
            line = tsv_data.readline()
            if not line:
                break
            await copy.write(line.encode())

    await conn.commit()

    # Verify
    cursor = await conn.execute("SELECT COUNT(*) FROM test_schema.copy_test WHERE id >= 4001")
    result = await cursor.fetchone()

    assert result[0] == 2


async def test_copy_with_null_values(db_connection):
    """Test COPY with NULL values."""
    conn = db_connection

    # Data with NULL (represented as \\N in COPY format, tab-delimited)
    data = io.StringIO("5001\tNullTest1\t\\N\n5002\tNullTest2\t100.00\n")

    # Copy data
    async with conn.cursor() as cur:
        async with cur.copy("COPY test_schema.copy_test (id, name, amount) FROM STDIN") as copy:
            while True:
                line = data.readline()
                if not line:
                    break
                await copy.write(line.encode())

    await conn.commit()

    # Verify NULL was imported
    cursor = await conn.execute("SELECT amount FROM test_schema.copy_test WHERE id = 5001")
    result = await cursor.fetchone()

    assert result[0] is None


async def test_copy_large_dataset(db_connection):
    """Test COPY with larger dataset."""
    conn = db_connection

    # Generate 1000 rows (tab-delimited)
    data = io.StringIO()
    for i in range(1000):
        data.write(f"{6000 + i}\tLargeRow{i}\t{100.0 + i}\n")
    data.seek(0)

    # Copy all data
    async with conn.cursor() as cur:
        async with cur.copy("COPY test_schema.copy_test (id, name, amount) FROM STDIN") as copy:
            while True:
                line = data.readline()
                if not line:
                    break
                await copy.write(line.encode())

    await conn.commit()

    # Verify count
    cursor = await conn.execute("SELECT COUNT(*) FROM test_schema.copy_test WHERE id >= 6000")
    result = await cursor.fetchone()

    assert result[0] == 1000


async def test_copy_specific_columns(db_connection):
    """Test COPY with specific column list."""
    conn = db_connection

    # Data for only name and amount (id will be auto-generated, tab-delimited)
    data = io.StringIO("SpecCol1\t150.00\nSpecCol2\t250.00\n")

    # Copy to specific columns
    async with conn.cursor() as cur:
        async with cur.copy("COPY test_schema.copy_test (name, amount) FROM STDIN") as copy:
            while True:
                line = data.readline()
                if not line:
                    break
                await copy.write(line.encode())

    await conn.commit()

    # Verify
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM test_schema.copy_test WHERE name LIKE 'SpecCol%'"
    )
    result = await cursor.fetchone()

    assert result[0] == 2
