# Proxy-Based Functional Tests

These tests validate the pygwire codec and state machine by running real PostgreSQL traffic through a transparent protocol proxy.

## How It Works

1. **Docker Compose** runs two services:
   - PostgreSQL server (port 5432)
   - Transparent proxy (port 5433)

2. **Tests** connect to PostgreSQL through the proxy using **psycopg3**

3. **Validation** is implicit:
   - ✅ Test passes = Proxy stayed alive = No state machine errors
   - ❌ Test fails = Proxy crashed (state machine error) or connection error

## Running Tests

### Start Services

```bash
docker-compose up -d
```

This starts:
- PostgreSQL on port 5432
- Proxy on port 5433 (with --strict mode)

### Run Tests

```bash
# All proxy functional tests
uv run pytest tests/proxy_functional/ -v

# Specific test file
uv run pytest tests/proxy_functional/test_simple_query.py -v

# Single test
uv run pytest tests/proxy_functional/test_simple_query.py::test_basic_select -v
```

### View Proxy Logs

```bash
# Real-time logs
docker-compose logs -f proxy

# Last 50 lines
docker-compose logs proxy --tail 50
```

### Stop Services

```bash
docker-compose down
```

## Test Structure

```
tests/proxy_functional/
├── conftest.py              # Fixtures for proxy and connections
├── test_simple_query.py     # Simple query protocol (10 tests)
└── README.md                # This file
```

## What's Being Tested

### Simple Query Protocol
- Basic SELECT/INSERT/UPDATE/DELETE
- Multiple rows, NULL handling
- Empty queries, multi-statement queries
- Aggregate functions
- WHERE clauses

## Key Features

### No Manual Protocol Implementation
- Uses psycopg3 (production-tested client)
- No custom `PostgreSQLConnection` wrapper
- Tests real-world protocol usage

### Strict Mode Validation
The proxy runs with `--strict` flag, which causes it to exit immediately on any `StateMachineError`. This makes validation simple and reliable.

### Fast and Reliable
- 10 tests run in ~0.14 seconds
- No flaky tests
- Clear failures with proxy logs

## Troubleshooting

### "Proxy not available" Error

Make sure docker-compose is running:
```bash
docker-compose ps
```

You should see both `pygwire_test_pg` and `pygwire_test_proxy` running.

### Check Proxy Health

```bash
# Check if proxy is accepting connections
nc -zv localhost 5433

# Check proxy logs for errors
docker-compose logs proxy
```

### Rebuild After Code Changes

If you modify `proxy.py` or `src/pygwire/`, rebuild the proxy:
```bash
docker-compose down
docker-compose build proxy
docker-compose up -d
```

## Design Philosophy

**Smoke Tests Only**: These tests validate that the protocol is correct (no state machine errors) but don't verify specific message sequences or internal state. They're designed to catch protocol violations, not implementation details.

For detailed protocol testing (message sequences, phase transitions, etc.), see the unit tests in `tests/unit/`.
