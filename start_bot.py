"""Preflight-checked observer/paper launcher; passes arguments to engine_v1.stream."""
import json
from pathlib import Path
import sys


def main():
    try:
        from doctor import check
        result = check(Path(__file__).resolve().parent, Path('data'))
        if not result['ready']:
            print(json.dumps(result, indent=2), file=sys.stderr)
            return 2
        from engine_v1.stream import main as stream_main
        stream_main()
        return 0
    except KeyboardInterrupt:
        print('Stopped by operator.', file=sys.stderr)
        return 130
    except (ImportError, OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        print(f'Startup/session stopped: {type(error).__name__}: {error}. Run python doctor.py and check the configuration and network. No automatic restart of failed financial state.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
