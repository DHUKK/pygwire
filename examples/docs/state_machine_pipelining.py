"""State machine: pending_syncs for extended query pipelining."""

from pygwire import ConnectionPhase, FrontendStateMachine
from pygwire.constants import TransactionStatus
from pygwire.messages import ReadyForQuery, Sync

sm = FrontendStateMachine(phase=ConnectionPhase.READY)

# Each Sync from READY (or from EXTENDED_QUERY without an active batch) creates
# one sync point that the server will acknowledge with a ReadyForQuery.
sm.send(Sync())  # pending_syncs → 1, phase → EXTENDED_QUERY
sm.send(Sync())  # pending_syncs → 2
print(sm.pending_syncs)  # 2

# Each ReadyForQuery resolves one sync point.
sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
print(sm.pending_syncs)  # 1
print(sm.phase)  # EXTENDED_QUERY (still waiting for one more ReadyForQuery)

sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
print(sm.pending_syncs)  # 0
print(sm.phase)  # READY
