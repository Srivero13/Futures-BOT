"""Research funding arithmetic; signed base quantity, positive cash means receipt."""
from decimal import Decimal, localcontext


def funding_cashflow(quantity, mark_price, rate):
    values = []
    for value in (quantity, mark_price, rate):
        if not isinstance(value, (str, Decimal)):
            raise ValueError('Use decimal strings or Decimal, not binary floats')
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError('Nonfinite funding input')
        values.append(number)
    quantity, mark_price, rate = values
    if mark_price <= 0:
        raise ValueError('Funding requires a positive settlement mark price')
    with localcontext() as context:
        context.prec = 50
        return -quantity * mark_price * rate


def event_exposure(entry_ms, exit_ms, funding_ms, guard_ms=60000):
    """Research convention only; ambiguous boundaries must not become zero fees."""
    if any(type(t) is not int for t in (entry_ms, exit_ms, funding_ms, guard_ms)):
        raise ValueError('Integer millisecond timestamps required')
    if entry_ms >= exit_ms or guard_ms < 0:
        raise ValueError('Invalid exposure interval or guard')
    if min(abs(funding_ms-entry_ms), abs(funding_ms-exit_ms)) <= guard_ms:
        return 'ambiguous'
    return 'held' if entry_ms < funding_ms < exit_ms else 'not_held'
