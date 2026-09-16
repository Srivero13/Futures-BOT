"""Bounded observer/paper progress on stderr, independent of trade decisions."""
import math
import sys
import time


class ProgressReporter:
    def __init__(self, interval=5., output=None, clock=None):
        if not math.isfinite(interval) or (interval != 0 and interval < 1):
            raise ValueError('Progress interval must be zero (quiet) or at least one second')
        self.interval = interval
        self.output = output if output is not None else sys.stderr
        self.clock = clock if clock is not None else time.monotonic
        self.last = None
        self.disabled = interval == 0

    def update(self, *, state, observe, elapsed, duration, messages, reconnects,
               errors, fresh, symbols, warm, clock_ok, force=False):
        if self.disabled:
            return
        now = self.clock()
        if not force and self.last is not None and now-self.last < self.interval:
            return
        elapsed = max(0., elapsed)
        total = f'{duration:.0f}s' if duration else 'continuous'
        remaining = f'{max(0., duration-elapsed):.0f}s' if duration else 'unlimited'
        mode = 'observe' if observe else 'paper'
        line = (f'[{mode}] {state} | elapsed={elapsed:.0f}s/{total} remaining={remaining} '
                f'| messages={messages:,} avg_msg/s={messages/elapsed if elapsed else 0:.1f} '
                f'| fresh_quotes={fresh}/{symbols} candles={warm}/21 '
                f'| reconnects={reconnects} errors={errors} clock_ok={clock_ok}')
        try:
            print(line, file=self.output, flush=True)
        except (OSError, ValueError):
            # Closed/broken console output must not trigger a feed reconnect.
            self.disabled = True
        self.last = now
