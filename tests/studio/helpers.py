import hashlib
import hmac
import json
from urllib.parse import urlencode

BOT_TOKEN = '123456:synthetic-test-token'


def signed_init(user_id=101, now=1_800_000_000, **extra):
    fields = {'auth_date': str(now), 'user': json.dumps({'id': user_id, 'first_name': 'Алия', 'username': 'client_demo'}, ensure_ascii=False, separators=(',', ':')), **extra}
    check = '\n'.join(f'{key}={value}' for key, value in sorted(fields.items()))
    secret = hmac.digest(b'WebAppData', BOT_TOKEN.encode(), 'sha256')
    fields['hash'] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)
