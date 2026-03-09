"""Index: Using the low-level API."""

from pygwire.codec import BackendMessageDecoder
from pygwire.messages import ParameterStatus, Query

# Decode server messages
decoder = BackendMessageDecoder()
ps = ParameterStatus(name="foo", value="bar")
data_from_server = ps.to_wire()

decoder.feed(data_from_server)
for msg in decoder:
    print(f"{type(msg).__name__}: {msg}")

# Encode client messages
query = Query(query_string="SELECT 1")
wire_bytes = query.to_wire()

print(wire_bytes)
