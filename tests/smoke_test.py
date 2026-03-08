"""Smoke test to verify the package installs and basic imports work."""

import pygwire
from pygwire.messages import Query

# Verify version is set
assert pygwire.__version__, "missing __version__"

# Verify basic message encoding round-trip
query = Query(query_string="SELECT 1")
wire = query.to_wire()
assert isinstance(wire, bytes)
assert len(wire) > 0

print(f"pygwire {pygwire.__version__} OK")
