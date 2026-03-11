"""State Machine: Error handling."""

from pygwire import FrontendStateMachine, StateMachineError
from pygwire.messages import Query

sm = FrontendStateMachine()

try:
    # Can't send a query before completing startup
    sm.send(Query(query_string="SELECT 1"))
except StateMachineError as e:
    print(f"Invalid: {e}")
