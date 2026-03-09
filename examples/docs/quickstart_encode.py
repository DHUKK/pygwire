"""Quickstart: Encoding messages."""

from pygwire.messages import Query, StartupMessage, Terminate

# Simple query
query = Query(query_string="SELECT * FROM users WHERE id = 1")
print(f"Query wire bytes: {query.to_wire()!r}")

# Startup message
startup = StartupMessage(params={"user": "postgres", "database": "mydb"})
print(f"Startup wire bytes ({len(startup.to_wire())} bytes)")

# Graceful disconnect
terminate = Terminate()
print(f"Terminate wire bytes: {terminate.to_wire()!r}")
