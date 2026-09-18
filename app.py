import os
import json
import datetime
import requests
from flask import Flask, jsonify, render_template, request, redirect

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

app = Flask(__name__)

SCOPES = [
  'https://www.googleapis.com/auth/calendar.readonly',
  'https://www.googleapis.com/auth/gmail.readonly'
]

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI')

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY')

PAYMENT_KEYWORDS = [
  '請求', '支払', 'お支払', '支払い', '払込', '振込', '引き落とし', '引落',
  'カード', 'ご利用', '利用額', '利用料', '料金', '未払', '督促', '期限',
  'invoice', 'payment', 'billing', 'due'
]


def _supabase_headers():
  return {
    'apikey': SUPABASE_SERVICE_KEY,
    'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
    'Content-Type': 'application/json'
  }


def kv_get(key, default=None):
  if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    return default
  try:
    res = requests.get(
      f'{SUPABASE_URL}/rest/v1/kv_store',
      headers=_supabase_headers(),
      params={'key': f'eq.{key}', 'select': 'value'},
      timeout=10
    )
    res.raise_for_status()
    rows = res.json()
    if rows:
      return rows[0]['value']
    return default
  except Exception:
    return default


def kv_set(key, value):
  if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    return False
  try:
    payload = {
      'key': key,
      'value': value,
      'updated_at': datetime.datetime.utcnow().isoformat()
    }
    res = requests.post(
      f'{SUPABASE_URL}/rest/v1/kv_store',
      headers={**_supabase_headers(), 'Prefer': 'resolution=merge-duplicates'},
      json=payload,
      timeout=10
    )
    res.raise_for_status()
    return True
  except Exception:
    return False


def get_credentials():
  token_json = kv_get('google_oauth_token')
  if not token_json:
    return None
  try:
    info = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(info, SCOPES)
  except Exception:
    return None
  if creds and creds.expired and creds.refresh_token:
    try:
      creds.refresh(GoogleAuthRequest())
      kv_set('google_oauth_token', creds.to_json())
    except Exception:
      return None
  return creds


@app.route('/')
def index():
  return render_template('index.html')


@app.route('/api/status')
def api_status():
  has_credentials = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI)
  is_valid = False
  if has_credentials:
    try:
      creds = get_credentials()
      is_valid = creds is not None and creds.valid
    except Exception:
      is_valid = False
  return jsonify({
    "has_credentials": has_credentials,
    "has_token": is_valid
  })


@app.route('/api/start-auth')
def start_auth():
  if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI):
    return jsonify({"error": "credentials_missing"}), 400
  client_config = {
    "web": {
      "client_id": GOOGLE_CLIENT_ID,
      "client_secret": GOOGLE_CLIENT_SECRET,
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token",
      "redirect_uris": [GOOGLE_REDIRECT_URI],
    }
  }
  flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=GOOGLE_REDIRECT_URI)
  authorization_url, _state = flow.authorization_url(
    access_type='offline',
    prompt='consent',
    include_granted_scopes='true'
  )
  return redirect(authorization_url)


@app.route('/api/oauth/callback')
def oauth_callback():
  error = request.args.get('error')
  if error:
    return f"<p>Googleとの連携がキャンセルされました（{error}）。<a href='/'>戻る</a></p>", 400
  code = request.args.get('code')
  if not code:
    return "<p>連携コードが見つかりませんでした。<a href='/'>戻る</a></p>", 400
  client_config = {
    "web": {
      "client_id": GOOGLE_CLIENT_ID,
      "client_secret": GOOGLE_CLIENT_SECRET,
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token",
      "redirect_uris": [GOOGLE_REDIRECT_URI],
    }
  }
  flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=GOOGLE_REDIRECT_URI)
  try:
    flow.fetch_token(code=code)
    creds = flow.credentials
    kv_set('google_oauth_token', creds.to_json())
  except Exception as e:
    return f"<p>連携に失敗しました：{e}</p><a href='/'>戻る</a>", 500
  return redirect('/')


@app.route('/api/data')
def api_data():
  creds = get_credentials()
  if not creds or not creds.valid:
    return jsonify({"error": "unauthorized"}), 410
  try:
    calendar_service = build('calendar', 'v3', credentials=creds)
    now = datetime.datetime.now()
    start_of_day = datetime.datetime(now.year, now.month, now.day, 0, 0, 0).astimezone().isoformat()
    end_of_day = datetime.datetime(now.year, now.month, now.day, 23, 59, 59).astimezone().isoformat()
    events_result = calendar_service.events().list(
      calendarId='primary',
      timeMin=start_of_day,
      timeMax=end_of_day,
      singleEvents=True,
      orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    formatted_events = []
    for event in events:
      start = event['start'].get('dateTime', event['start'].get('date'))
      all_day = 'date' in event['start']
      start_time = "終日"
      if not all_day:
        start_dt = datetime.datetime.fromisoformat(start)
        start_time = start_dt.strftime('%H:%M')
      formatted_events.append({
        "summary": event.get('summary', '（件名なし）'),
        "display_time": start_time,
        "all_day": all_day
      })

    gmail_service = build('gmail', 'v1', credentials=creds)
    messages_result = gmail_service.users().messages().list(
      userId='me',
      q='is:unread newer_than:14d',
      maxResults=25
    ).execute()
    messages = messages_result.get('messages', [])

    payment_mail = []
    for message in messages:
      msg = gmail_service.users().messages().get(
        userId='me',
        id=message['id'],
        format='metadata',
        metadataHeaders=['Subject', 'From', 'Date']
      ).execute()
      headers = msg.get('payload', {}).get('headers', [])
      subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '（件名なし）')
      sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), '（差出人不明）')
      date_str = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')
      snippet = msg.get('snippet', '')
      haystack = f"{subject} {snippet}"
      if not any(kw in haystack for kw in PAYMENT_KEYWORDS):
        continue
      if ' <' in sender:
        sender = sender.split(' <')[0].replace('"', '')
      payment_mail.append({
        "subject": subject,
        "from": sender,
        "date": date_str,
        "snippet": snippet
      })
      if len(payment_mail) >= 5:
        break

    return jsonify({
      "calendar": formatted_events,
      "payment_mail": payment_mail
    })
  except Exception as e:
    return jsonify({"error": str(e)}), 500


@app.route('/api/memo', methods=['GET'])
def get_memo():
  text = kv_get('memo', default='')
  return jsonify({"text": text})


@app.route('/api/memo', methods=['POST'])
def save_memo():
  data = request.get_json(silent=True) or {}
  text = data.get('text', '')
  ok = kv_set('memo', text)
  if not ok:
    return jsonify({"status": "error"}), 500
  return jsonify({"status": "ok"})


if __name__ == '__main__':
  app.run(debug=True, port=5000)
