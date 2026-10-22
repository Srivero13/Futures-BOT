import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from register_weekly_btc_forward import FILES, PLAN, register


class RegistrationTests(unittest.TestCase):
    def fixture(self, root):
        protocol=Path(__file__).resolve().parents[1]/FILES[0]
        contents={name:b'fixture source\n' for name in FILES}
        contents[FILES[0]]=protocol.read_bytes()
        protocol_hash=hashlib.sha256(contents[FILES[0]]).hexdigest()
        code={name:hashlib.sha256(contents[name]).hexdigest() for name in FILES[1:5]}
        development=dict(approved=False,experiment='WBC01',protocol_sha256=protocol_hash,
                         summary=dict(screen_failures=[]),code_sha256=code)
        contents[FILES[-2]]=json.dumps(development).encode()
        risk=dict(approved=False,experiment='WBC01',protocol_sha256=protocol_hash,
                  source_report_sha256=hashlib.sha256(contents[FILES[-2]]).hexdigest(),
                  code_sha256=code,scenarios={n:dict(terminal_reconciled=True) for n in ('base','stress','buy_and_hold')})
        contents[FILES[-1]]=json.dumps(risk).encode()
        for name,data in contents.items():
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        manifest=dict(approved=False,experiment='WBC01',files={n:hashlib.sha256(d).hexdigest() for n,d in contents.items()})
        (root/'manifest.json').write_text(json.dumps(manifest))
        return manifest

    def test_registration_is_read_only_and_before_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result=register(root,datetime(2026,10,21,tzinfo=timezone.utc))
            self.assertEqual(result['status'],'registered_pending_future_data')
            self.assertFalse(result['approved'])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            with self.assertRaises(ValueError): register(root,datetime(2026,10,26,tzinfo=timezone.utc))

    def test_modified_file_and_code_binding_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest=self.fixture(root)
            (root/FILES[1]).write_text('changed')
            now=datetime(2026,10,21,tzinfo=timezone.utc)
            with self.assertRaises(ValueError): register(root,now)
            manifest['files'][FILES[1]]=hashlib.sha256(b'changed').hexdigest()
            (root/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): register(root,now)

    def test_fixed_calendar_has_26_weeks_and_correct_warmup(self):
        from datetime import timedelta
        plan=json.loads(PLAN.read_text())
        start=datetime.fromisoformat(plan['evaluation_start_utc'])
        end=datetime.fromisoformat(plan['evaluation_end_exclusive_utc'])
        self.assertEqual(start.weekday(),0)
        self.assertEqual(end-start,timedelta(weeks=26))
        self.assertEqual(datetime.fromisoformat(plan['warmup_start_utc']),start-timedelta(days=7,minutes=1))
        self.assertEqual(datetime.fromisoformat(plan['terminal_reference_utc']),end-timedelta(minutes=1))
