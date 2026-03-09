"""State Machine: Error handling."""

from pygwire.messages import Query
from pygwire.state_machine import FrontendStateMachine, StateMachineError

sm = FrontendStateMachine()

try:
    # Can't send a query before completing startup
    sm.send(Query(query_string="SELECT 1"))
except StateMachineError as e:
    print(f"Invalid: {e}")
