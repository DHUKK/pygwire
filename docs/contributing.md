# Contributing

Thanks for your interest in contributing to pygwire!

## Development setup

pygwire uses [uv](https://docs.astral.sh/uv/) as its package manager.

```bash
git clone https://github.com/DHUKK/pygwire.git
cd pygwire
uv sync
```

## Running tests

```bash
# Unit + integration tests
uv run pytest tests/unit/ tests/integration/ -v

# Or use the Makefile
make test
```

### Proxy functional tests

These run against a real PostgreSQL instance through a transparent protocol proxy. Requires Docker.

```bash
# Start PostgreSQL and proxy
docker compose -f tests/infrastructure/docker-compose.yml up -d

# Run functional tests
uv run pytest tests/proxy_functional/ -v

# Stop services
docker compose -f tests/infrastructure/docker-compose.yml down -v
```

Test against a specific PostgreSQL version (13-18):

```bash
POSTGRES_VERSION=15 docker compose -f tests/infrastructure/docker-compose.yml up -d
```

## Code quality

```bash
# Lint + type check
make check

# Auto-format
make format

# Or individually
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

## Pull request guidelines

1. Run `make check` and `make test` before submitting
2. Add tests for new functionality
3. Follow existing code patterns and naming conventions
4. Keep PRs focused: one feature or fix per PR

## Project conventions

- **PostgreSQL naming**: "backend" = server, "frontend" = client
- **Private modules**: message implementations live in `_*.py` files; the public API is `pygwire.messages`
- **Sans-I/O**: the core library must not perform any I/O operations
- **Zero-copy**: use `memoryview` for buffer slicing in hot paths
