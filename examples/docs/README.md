# Documentation Examples

This directory contains runnable Python scripts for all code examples used in the documentation. This ensures that examples in the docs are accurate and show real, working code.

## Structure

Each example script corresponds to a code block in the documentation:

- `quickstart_*.py` - Examples from `docs/quickstart.md`
- `codec_*.py` - Examples from `docs/reference/codec.md`
- `state_machine_*.py` - Examples from `docs/reference/state-machine.md`
- `connection_*.py` - Examples from `docs/reference/connection.md`
- `index_*.py` - Examples from `docs/index.md`

## Usage

Run individual examples:

```bash
uv run python quickstart_verify.py
uv run python codec_basic_usage.py
```

Test all examples at once:

```bash
bash test_all_examples.sh
```

**Note:** Some examples (`index_connection.py`, `index_subclass.py`) require an actual PostgreSQL server connection and are skipped in automated tests. These examples show the real code as you would use it, with placeholder values like `socket.create_connection(("localhost", 5432))` that you would replace in production.

## Documentation Integration

The documentation uses MkDocs snippets to include these files:

```markdown
\`\`\`python
--8<-- "examples/docs/quickstart_verify.py"
\`\`\`
```

This ensures documentation stays in sync with working code. When we update an example, the docs automatically reflect the change.
