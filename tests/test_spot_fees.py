import hashlib
import hmac
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
from read_spot_fees import query_rates,sanitize,NoRedirect,fetch


def fixture():
    return {'symbol':'ETHUSDT',**{c:{s:'0.001' for s in ('maker','taker','buyer','seller')} for c in ('standardCommission','taxCommission','specialCommission')},
        'discount':{'enabledForAccount':True,'enabledForSymbol':True,'discountAsset':'BNB','discount':'0.25'},'apiKey':'must-not-survive','balances':[123]}


class FeeReaderTests(unittest.TestCase):
    def test_signed_get_routes_and_whitelist(self):
        key='K'*64;secret='S'*64
        with patch('read_spot_fees.fetch',side_effect=[{'serverTime':123456},fixture()]) as f:
            result=query_rates('ETHUSDT',key,secret)
        self.assertEqual(f.call_args_list[0].args,('/api/v3/time',))
        path,query,header=f.call_args_list[1].args
        self.assertEqual(path,'/api/v3/account/commission');self.assertEqual(header,key)
        plain,sig=query.rsplit('&signature=',1)
        self.assertEqual(sig,hmac.new(secret.encode(),plain.encode(),hashlib.sha256).hexdigest())
        self.assertEqual(parse_qs(plain)['symbol'],['ETHUSDT'])
        self.assertNotIn('apiKey',result);self.assertNotIn('balances',result)
        self.assertNotIn(secret,json.dumps(result))

    def test_invalid_rates_and_symbol(self):
        for value in ('NaN','Infinity','-0.1','2'):
            r=fixture();r['standardCommission']['taker']=value
            with self.assertRaises(ValueError):sanitize(r,'ETHUSDT')
        with self.assertRaises(ValueError):sanitize(fixture(),'BTCUSDT')
        with self.assertRaises(ValueError):fetch('/api/v3/order')

    def test_redirects_refused(self):
        with self.assertRaises(RuntimeError):NoRedirect().redirect_request(None,None,302,'',{},'https://example.com')
