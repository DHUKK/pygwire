"""Quickstart: Verify installation."""

from pygwire.messages import Query

query = Query(query_string="SELECT 1")
print(query.to_wire())  # Raw wire protocol bytes
