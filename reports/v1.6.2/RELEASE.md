# Version 1.6.2 — distinguish completion from feed failure

The observer bounds each socket read by the remaining finite-session duration. In 1.6.1, expiration of the last read could be counted as WebSocketTimeoutException and a reconnect at exactly the requested end time, even though the session was simply completing.

Version 1.6.2 exits the receive loop normally when that read timeout occurs at or after the finite-session deadline. It also checks the remaining budget before configuring a read timeout. Earlier read timeouts, continuous-session timeouts, connection establishment failures, and other errors retain existing handling. Normal shutdown still closes the socket and publishes stopped health.

Validation: 113 tests run; 112 passed and the optional Numba test skipped. Three new mocked-clock/WebSocket tests verify normal deadline completion without a false reconnect, recovery after an earlier timeout, and recovery in continuous mode. No live test on deployment hardware was performed for this patch. The reported user session received 9,901 messages and logged its sole read timeout at the 60-second deadline; that observation motivated the regression tests, not a claim that every earlier timeout had the same cause.

No training, model artifacts, dataset, dependencies, accounting or trading decision changes. Pull after active sessions finish; the next launch uses the fix.
