"""Two simulated spot accounts with shared admission controls; offline only."""
import argparse
import json
from decimal import Decimal as D
from importlib.metadata import version
from pathlib import Path


class Admission:
    """In-memory, single-event-loop control. Retain reservations until confirmed flat."""
    def __init__(self):
        self.paused = False
        self.last = {}
        self.reserved = {}
        self.seen = set()
        self.exits_pending = set()
        self.audit = []
        self.peak_reserved = D(0)

    def request(self, account, event, now, notional, *, exit=False):
        if (account not in ('A', 'B') or not isinstance(event, str) or not event or
                type(now) is not int or now < 0 or not isinstance(notional, D) or
                not notional.is_finite() or notional <= 0):
            raise ValueError('Invalid request')
        key = (account, event)
        if key in self.seen:
            reason = 'duplicate'
        elif self.paused and not exit:
            reason = 'paused'
        elif any(s not in self.last or not 0 <= now-self.last[s] <= 1_000_000_000
                 for s in ((account,) if exit else ('A', 'B'))):
            reason = 'stale_quotes'
        elif exit and account in self.exits_pending:
            reason = 'exit_pending'
        elif exit and account not in self.reserved:
            reason = 'no_position'
        elif not exit and notional > D('120'):
            reason = 'account_cap'
        elif not exit and sum(self.reserved.values(), D(0))+notional > D('150'):
            reason = 'global_cap'
        elif not exit and account in self.reserved:
            reason = 'position_or_order_pending'
        else:
            reason = 'accepted'
            self.seen.add(key)
            if exit:
                self.exits_pending.add(account)
            if not exit:
                self.reserved[account] = notional
                self.peak_reserved = max(self.peak_reserved, sum(self.reserved.values(), D(0)))
        self.audit.append(dict(account=account, event=event, reason=reason, exit=exit,
                               reserved=str(sum(self.reserved.values(), D(0)))))
        return reason == 'accepted'

    def confirm_flat(self, account):
        del self.reserved[account]
        self.exits_pending.discard(account)


def run(gate=None):
    if version('nautilus_trader') != '1.231.0':
        raise ValueError('Expected NautilusTrader 1.231.0')
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
    from nautilus_trader.model.currencies import ETH, USDT
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.model.instruments import CurrencyPair
    from nautilus_trader.model.objects import Money, Price, Quantity
    from nautilus_trader.trading.strategy import Strategy

    gate = Admission() if gate is None else gate
    if gate.reserved or gate.seen:
        raise ValueError("Paper fixture requires a fresh admission state")
    ids = {a: InstrumentId.from_str('ETHUSDT.SIM'+a) for a in ('A', 'B')}
    instruments = [CurrencyPair(instrument_id=iid, raw_symbol=Symbol('ETHUSDT'),
        base_currency=ETH, quote_currency=USDT, price_precision=2, size_precision=6,
        price_increment=Price.from_str('0.01'), size_increment=Quantity.from_str('0.000001'),
        maker_fee=D('0.001'), taker_fee=D('0.001'), ts_event=0, ts_init=0) for iid in ids.values()]

    class Controlled(Strategy):
        def __init__(self):
            super().__init__()
            self.fills = []
            self.quotes = {}
            self.holdings = dict(A=D(0), B=D(0))

        def on_start(self):
            for iid in ids.values():
                self.subscribe_quote_ticks(iid)

        def attempt(self, account, event, qty, now, exit=False):
            quote = self.quotes[account]
            # Fixed fixture: fee-inclusive order budget, zero extra slippage.
            amount = qty*quote.ask_price.as_decimal()*D('1.001')
            if gate.request(account, event, now, amount, exit=exit):
                self.submit_order(self.order_factory.market(instrument_id=ids[account],
                    order_side=OrderSide.SELL if exit else OrderSide.BUY,
                    quantity=Quantity.from_str(f'{qty:.6f}')))

        def on_quote_tick(self, quote):
            account = 'A' if quote.instrument_id == ids['A'] else 'B'
            self.quotes[account] = quote
            now = quote.ts_init
            gate.last[account] = now
            second = now//1_000_000_000
            if second == 2 and account == 'B':
                self.attempt('A', 'oversize', D('2'), now)
                self.attempt('A', 'enter-a', D('1'), now)
                self.attempt('A', 'enter-a', D('1'), now)
                self.attempt('B', 'over-global', D('0.3'), now)
                self.attempt('B', 'enter-b', D('0.2'), now)
            elif second == 3:
                gate.paused = True
                self.attempt('A', 'while-paused', D('0.01'), now)
            elif second == 4:
                gate.paused = False
                self.attempt('A', 'while-b-stale', D('0.01'), now)
                self.attempt('B', 'stale-exit', D('0.2'), now, exit=True)
            elif second == 5:
                gate.paused = True
                self.attempt('B', 'exit-b', D('0.2'), now, exit=True)
            elif second == 6:
                self.attempt('A', 'exit-a', D('1'), now, exit=True)

        def on_order_filled(self, event):
            account = 'A' if event.instrument_id == ids['A'] else 'B'
            qty = event.last_qty.as_decimal()
            self.holdings[account] += qty if event.order_side == OrderSide.BUY else -qty
            self.fills.append(dict(account=account, engine_account=str(event.account_id),
                side=event.order_side.name, quantity=str(qty), price=str(event.last_px),
                fee=str(event.commission.as_decimal()), fee_currency=str(event.commission.currency)))
            if event.order_side == OrderSide.SELL and self.holdings[account] == 0:
                gate.confirm_flat(account)

    # No B quotes at seconds 3/4: only A is fresh. Exit requests must respect this.
    fixture = [('A', 1, '100.00'), ('B', 1, '200.00'),
               ('A', 2, '100.00'), ('B', 2, '200.00'),
               ('A', 3, '100.00'), ('A', 4, '100.00'),
               ('B', 5, '199.00'), ('A', 6, '101.00'),
               ('B', 7, '199.00'), ('A', 7, '101.00')]
    strategy = Controlled()
    engine = BacktestEngine(BacktestEngineConfig(logging=LoggingConfig(log_level='ERROR')))
    try:
        for account in ('A', 'B'):
            engine.add_venue(venue=ids[account].venue, oms_type=OmsType.NETTING,
                account_type=AccountType.CASH, starting_balances=[Money(1000, USDT)])
        for instrument in instruments:
            engine.add_instrument(instrument)
        engine.add_data([QuoteTick(ids[a], Price.from_str(bid), Price.from_str(f'{D(bid)+D("0.10"):.2f}'),
            Quantity.from_str('100.000000'), Quantity.from_str('100.000000'), sec*10**9, sec*10**9)
            for a, sec, bid in fixture])
        engine.add_strategy(strategy)
        engine.run()
        balances = {a: engine.cache.account_for_venue(ids[a].venue).balance_total(USDT).as_decimal()
                    for a in ('A', 'B')}
        open_positions = len(engine.cache.positions_open())
        orders = engine.cache.orders()
    finally:
        engine.dispose()
    outcomes = {r['event']: r['reason'] for r in gate.audit}
    checks = dict(account_cap_blocks=outcomes['oversize'] == 'account_cap',
        pending_orders_count_towards_global_cap=outcomes['over-global'] == 'global_cap',
        duplicate_entry_blocked=any(r['event'] == 'enter-a' and r['reason'] == 'duplicate' for r in gate.audit),
        pause_blocks_entries=outcomes['while-paused'] == 'paused',
        either_feed_stale_blocks_entries=outcomes['while-b-stale'] == 'stale_quotes',
        stale_exit_blocked=outcomes['stale-exit'] == 'stale_quotes',
        fresh_exits_allowed_while_paused=outcomes['exit-a'] == outcomes['exit-b'] == 'accepted',
        exactly_four_filled_orders=len(orders) == len(strategy.fills) == 4,
        independent_account_balances=balances == {'A': D('1000.6989'), 'B': D('999.70018')},
        separate_engine_accounts=len({r['engine_account'] for r in strategy.fills}) == 2,
        both_accounts_flat=open_positions == 0 and not gate.reserved and all(q == 0 for q in strategy.holdings.values()),
        reservation_cap_respected=gate.peak_reserved <= D('150'))
    if not all(checks.values()):
        raise ValueError(f'Paper control failed: {checks}; balances={balances}; fills={strategy.fills}')
    return dict(approved=False, real_orders=False, synthetic=True, status='two_account_paper_control_passed',
        checks=checks, balances={k: str(v) for k, v in balances.items()}, fills=strategy.fills,
        admission_log=gate.audit, peak_reserved_quote=str(gate.peak_reserved),
        limitations=['Two synthetic spot venues in one offline engine; not two live Binance accounts.',
                    'Admission reserves fixed entry budgets, not mark-to-market risk or liquidation margin.',
                    'In-memory single-loop control; restart persistence, partial/rejected orders and live integration remain pending.',
                    'Synthetic engineering signals and fills; no strategy or profitability evidence.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Output exists; use a new path.')
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
