"""Read Binance Spot commission rates locally; no order or balance requests."""
import argparse
from decimal import Decimal
import getpass
import hashlib
import hmac
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from engine_v1.operations import atomic_json

BASE='https://api.binance.com'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise RuntimeError('Redirect refused')


def fetch(path,query='',key=None):
    if path not in ('/api/v3/time','/api/v3/account/commission'):raise ValueError('Endpoint not allowed')
    request=urllib.request.Request(BASE+path+('?' + query if query else ''),method='GET')
    if key is not None:request.add_header('X-MBX-APIKEY',key)
    # No redirects or environment proxies carrying signed URLs/headers.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(request,timeout=10) as response:
            raw=response.read(65537)
        if len(raw)>65536:raise RuntimeError('Response too large')
        result=json.loads(raw)
        if not isinstance(result,dict):raise RuntimeError('Unexpected response')
        return result
    except urllib.error.HTTPError as error:
        # Never print a signed URL, request headers, or raw error body.
        code=error.code;error.close()
        raise RuntimeError(f'Binance HTTP {code}; check read permission, key type, IP restrictions and connectivity') from None
    except (urllib.error.URLError,OSError,ValueError):
        raise RuntimeError('Network or response parsing failed; sensitive request details omitted') from None


def rate(value):
    x=Decimal(str(value))
    if not x.is_finite() or x<0 or x>1:raise ValueError('Invalid commission rate')
    return format(x,'f')


def sanitize(data,symbol):
    if data.get('symbol')!=symbol:raise ValueError('Unexpected response symbol')
    result={'symbol':symbol}
    for category in ('standardCommission','taxCommission','specialCommission'):
        result[category]={side:rate(data[category][side]) for side in ('maker','taker','buyer','seller')}
    discount=data['discount']
    for flag in ('enabledForAccount','enabledForSymbol'):
        if type(discount[flag]) is not bool:raise ValueError('Invalid discount flags')
    asset=discount['discountAsset']
    if not isinstance(asset,str) or not re.fullmatch('[A-Z0-9]{1,20}',asset):raise ValueError('Invalid discount asset')
    result['discount']={flag:discount[flag] for flag in ('enabledForAccount','enabledForSymbol')}
    result['discount'].update(discountAsset=asset,discount=rate(discount['discount']))
    return result


def query_rates(symbol,key,secret):
    if not re.fullmatch('[A-Z0-9]{5,20}',symbol):raise ValueError('Invalid symbol')
    if not all(re.fullmatch('[A-Za-z0-9]{16,128}',v) for v in (key,secret)):raise ValueError('Expected HMAC API key and secret')
    start=time.monotonic();server=fetch('/api/v3/time');elapsed=time.monotonic()-start
    stamp=server.get('serverTime')
    if type(stamp) is not int or stamp<=0 or elapsed>3:raise ValueError('Server-time check failed or was too slow; retry later')
    query=urllib.parse.urlencode({'symbol':symbol,'recvWindow':5000,'timestamp':stamp})
    signature=hmac.new(secret.encode(),query.encode(),hashlib.sha256).hexdigest()
    data=fetch('/api/v3/account/commission',query+'&signature='+signature,key)
    return sanitize(data,symbol)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--symbol',default='ETHUSDT');p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    try:
        if a.output.exists():raise ValueError('Output exists; choose a new filename')
        if not sys.stdin.isatty():raise ValueError('Use an interactive terminal for private credential prompts')
        with warnings.catch_warnings():
            warnings.simplefilter('error',getpass.GetPassWarning)
            key=getpass.getpass('Read-only HMAC API key (hidden): ')
            secret=getpass.getpass('API secret (hidden): ')
        rates=query_rates(a.symbol,key,secret)
        key=secret=None  # No credential persistence; Python memory is not securely erased.
        report={'approved':False,'market':'spot','observed_at_unix_ms':time.time_ns()//1_000_000,
            'endpoint':'GET /api/v3/account/commission','rates':rates,
            'note':'Raw account/symbol rates; discounts are conditional. No effective-fee calculation, balance query, orders or model changes.'}
        atomic_json(a.output,report);print(json.dumps(report,indent=2))
        return 0
    except (KeyboardInterrupt,EOFError):print('Fee query cancelled.',file=sys.stderr);return 130
    except Exception:
        # Prompt/backend failures can contain credentials. Keep CLI errors generic.
        print('Fee query failed. Check output path, interactive terminal, read-only HMAC credentials, IP restrictions and connection. No sensitive details printed.',file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
