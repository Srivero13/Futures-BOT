"""Keep local persistence failures out of network retry handlers."""
import sqlite3


class LocalRuntimeError(RuntimeError):
    """A local operation failed; reconnecting the market feed cannot repair it."""


def local_operation(label, operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except (OSError, sqlite3.Error, ValueError) as error:
        raise LocalRuntimeError(
            f'{label} failed ({type(error).__name__}); run stopped, not retried as a feed outage'
        ) from error
