# Contributing to pygwire

Thanks for your interest in contributing! This guide covers the development setup and workflow.

## Development Setup

pygwire uses [uv](https://docs.astral.sh/uv/) as its package manager.

```bash
# Clone the repository
git clone https://github.com/DHUKK/pygwire.git
cd pygwire

# Install dependencies (creates a virtual environment automatically)
uv sync
```

## Running Tests

```bash
# Unit tests
uv run pytest tests/unit/ -v

# Integration tests
uv run pytest tests/integration/ -v

# All local tests (unit + integration)
make test
```

### Proxy Functional Tests

These tests run against a real PostgreSQL instance through a protocol proxy. They require Docker.

```bash
# Start PostgreSQL and proxy containers
docker compose -f tests/infrastructure/docker-compose.yml up -d

# Wait for services to be healthy, then run tests
make test-functional

# Stop services
docker compose -f tests/infrastructure/docker-compose.yml down -v
```

To test against a specific PostgreSQL version (13-18):

```bash
POSTGRES_VERSION=15 docker compose -f tests/infrastructure/docker-compose.yml up -d
```

## Code Quality

```bash
# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/

# Type check
uv run mypy src/

# Run all checks
make check
```

## Pull Request Guidelines

1. Run `make check` and `make test` before submitting
2. Add tests for new functionality
3. Follow existing code patterns and naming conventions
4. Keep PRs focused -- one feature or fix per PR

## Project Conventions

- **PostgreSQL naming**: "backend" = server, "frontend" = client
- **Private modules**: Message implementations live in `_*.py` files; the public API is `pygwire.messages`
- **Sans-I/O**: Core library must not perform any I/O operations
