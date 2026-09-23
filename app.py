import os
import json
import datetime
import unicodedata
from zoneinfo import ZoneInfo
import requests
from flask import Flask, jsonify, render_template, request, redirect

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

app = Flask(__name__)

JST = ZoneInfo('Asia/Tokyo')

SCOPES = [
  'https://www.googleapis.com/auth/calendar.readonly',
  'https://www.googleapis.com/auth/gmail.readonly'
]

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI')

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY')

JST_WEEKDAYS = ['月', '火', '水', '木', '金', '土', '日']

DEADLINE_LOOKAHEAD_DAYS = 60  # 「近づいている期限」で、今日から何日先まで見るか
DEADLINE_COLOR_ID = '11'      # Googleカレンダーの「トマト(赤)」色に対応するID
DEADLINE_SOON_DAYS = 7        # 残り日数がこれ以下なら目立たせる

# 「口座振替予定のお知らせ」等、お金が自動で引かれる予定を知らせるメール。
# これに当たったら他のカテゴリより先に、画面いちばん上の専用の赤枠に出す
# （銀行・支払いカテゴリには入れず、二重に出さない）。
DIRECT_DEBIT_KEYWORDS = [
  '口座振替', '口座振替のお知らせ', '口座振替予定', '自動振替', '振替予定日',
]

# 「発送・配達」に当たったメールのうち、お届けが完了したことを知らせるメール。
# ここに当たれば「お届け完了」、当たらなければ「発送済み（進行中）」として数える。
DELIVERED_KEYWORDS = [
  '配達済み', 'お届け完了', 'お届けしました', '配送済み', 'delivered',
]


def _normalize(text):
  # 全角英数字を半角に、大文字を小文字にそろえる。
  # （例：「ＳＢＩ証券」→「sbi証券」、「Vercel」「vercel.com」→ どちらも「vercel」）
  # これをしないと、キーワードと表記が少しでも違うだけでメールが検知されず、
  # 見た目には何も起きていないのに実は非表示になってしまう。
  return unicodedata.normalize('NFKC', text).lower()

# 表示する（＝重要）メールのカテゴリ。件名・本文の一部・差出人のどこかに
# 1つでも当てはまれば、そのカテゴリとして画面に出す。
# 「注文確認・メルマガ・セール・おすすめ・ニュース」等はここに載っていない
# ＝どのカテゴリにも当たらないので、そのまま自動的に非表示になる。
MAIL_CATEGORIES = [
  {
    "label": "銀行・支払い",
    "keywords": [
      '請求書', 'ご請求', '請求金額', '支払', 'お支払い', '支払い期限', '払込', '振込',
      '引き落とし', '引落', '未払い', '未払', '督促',
      'ご利用料金のお知らせ', '利用明細', 'カードご利用', 'クレジットカード利用',
      'invoice', 'payment', 'billing', 'payment due',
      'ドコモSMTBネット銀行', '住信SBIネット銀行', 'NTTファイナンス', 'SBI証券',
    ]
  },
  {
    "label": "AI関連",
    "keywords": [
      'Anthropic', 'Claude', 'OpenAI', 'ChatGPT', 'GPT-', 'GPT4', 'GPT5', 'Gemini',
    ]
  },
  {
    "label": "セキュリティ通知",
    "keywords": [
      '不正', '認証コード', '確認コード', 'ワンタイム',
      '本人確認をお願いします', '本人確認が必要です', '本人確認をしてください',
      'パスワード', '心当たりのない', 'アクセスを検出', 'アクセスがありました',
      'ログインを検知', 'ログイン通知', '新しいログインがありました', '見慣れない場所からのログイン',
      'パスキー', 'セキュリティ通知', 'アクセスを許可しました', '共有しました',
      '再設定用のメールアドレス', 'アカウントが復元されました',
      'security', 'verification code', 'suspicious',
    ]
  },
  {
    "label": "システム",
    "keywords": [
      'GitHub', 'Vercel', 'Supabase',
      'デプロイ', 'ビルドが失敗', 'ビルドエラー', 'サーバー障害', 'メンテナンスのお知らせ',
      'Google Apps Script', 'Apps Script', 'Summary of failures', 'has failed to finish',
    ]
  },
  {
    "label": "発送・配達",
    "keywords": [
      '発送', '配達', 'お届け', '配送', '出荷', 'お荷物', '配達予定', '追跡番号',
      'delivery', 'shipped',
    ]
  },
  {
    "label": "旅行・交通",
    "keywords": [
      'ご予約', '搭乗', '航空券', '新幹線', '宿泊', 'チェックイン',
      'スカイマーク', 'JAL', 'ANA',
    ]
  },
  {
    "label": "病院・健康",
    "keywords": [
      '診察', '受診', '健康診断', '検査結果', 'クリニック', '通院',
    ]
  },
]

# 宣伝・お知らせ系のメールによく出る言い回し。これが件名・本文・差出人のどこかに
# 1つでも当てはまったら、他のキーワードに当てはまっても「確認が必要なメール」には出さない。
# （例：新機能の紹介メールが「パスワード」「ログイン」等の言葉を含み、誤って表示されるのを防ぐ）
PROMOTIONAL_MARKERS = [
  '対応スタート', '新機能', 'キャンペーン', 'ご利用いただけます', 'カイゼンLog',
  'メールマガジン', 'お客さまの声',
]


def _parse_event_start(event):
  # イベントの開始日時を、表示用の時刻と日付に分ける。終日予定は時刻の代わりに"終日"を返す。
  start = event['start'].get('dateTime', event['start'].get('date'))
  if 'date' in event['start']:
    return "終日", datetime.date.fromisoformat(start), True
  start_dt = datetime.datetime.fromisoformat(start)
  return start_dt.strftime('%H:%M'), start_dt.date(), False


def _format_date_label(date_obj):
  return f"{date_obj.month}/{date_obj.day}({JST_WEEKDAYS[date_obj.weekday()]})"


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
    now = datetime.datetime.now(JST)
    start_of_day = datetime.datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=JST).isoformat()
    range_end_day = datetime.datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=JST) + datetime.timedelta(days=6)
    end_of_day = range_end_day.isoformat()
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
      start_time, start_date, all_day = _parse_event_start(event)
      formatted_events.append({
        "summary": event.get('summary', '（件名なし）'),
        "display_time": start_time,
        "date_label": _format_date_label(start_date),
        "all_day": all_day
      })

    # ⏰ 近づいている期限：赤色（colorId "11"）の予定を、今日からDEADLINE_LOOKAHEAD_DAYS日先まで
    today_date = now.date()
    deadline_range_end = datetime.datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=JST) + datetime.timedelta(days=DEADLINE_LOOKAHEAD_DAYS)
    deadline_events_result = calendar_service.events().list(
      calendarId='primary',
      timeMin=start_of_day,
      timeMax=deadline_range_end.isoformat(),
      singleEvents=True,
      orderBy='startTime'
    ).execute()

    deadlines = []
    for event in deadline_events_result.get('items', []):
      if event.get('colorId') != DEADLINE_COLOR_ID:
        continue
      _, deadline_date, _ = _parse_event_start(event)
      days_left = (deadline_date - today_date).days
      deadlines.append({
        "summary": event.get('summary', '（件名なし）'),
        "date_label": _format_date_label(deadline_date),
        "days_label": "今日" if days_left == 0 else f"あと{days_left}日",
        "soon": days_left <= DEADLINE_SOON_DAYS
      })

    # 📖 昨日：Googleカレンダーの予定（時刻順）
    yesterday_date = today_date - datetime.timedelta(days=1)
    yesterday_start = datetime.datetime(yesterday_date.year, yesterday_date.month, yesterday_date.day, 0, 0, 0, tzinfo=JST)
    yesterday_end = datetime.datetime(yesterday_date.year, yesterday_date.month, yesterday_date.day, 23, 59, 59, tzinfo=JST)
    yesterday_events_result = calendar_service.events().list(
      calendarId='primary',
      timeMin=yesterday_start.isoformat(),
      timeMax=yesterday_end.isoformat(),
      singleEvents=True,
      orderBy='startTime'
    ).execute()

    yesterday_events = []
    for event in yesterday_events_result.get('items', []):
      start_time, _, all_day = _parse_event_start(event)
      yesterday_events.append({
        "summary": event.get('summary', '（件名なし）'),
        "display_time": start_time,
        "all_day": all_day
      })

    # 未読メールは14日間、既読になったメールも直近7日間は表示を続ける。
    # （カズさんの体調・記憶の事情に合わせて、既読にした直後に画面から消えないようにする対応）
    # 「newer_than:7d」は既読・未読を問わず全メールにかかるため、
    # 直近7日間に届く全メール数（実測で最大47件程度）が取得枠に収まるよう
    # maxResultsも合わせて広げてある。
    gmail_service = build('gmail', 'v1', credentials=creds)
    messages_result = gmail_service.users().messages().list(
      userId='me',
      q='({is:unread newer_than:14d} OR newer_than:7d) -in:draft',
      maxResults=60
    ).execute()
    messages = messages_result.get('messages', [])

    payment_mail = []
    direct_debit_mail = []
    shipped_count = 0
    delivered_count = 0
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
      haystack = _normalize(f"{subject} {snippet} {sender}")

      if ' <' in sender:
        sender = sender.split(' <')[0].replace('"', '')

      # 最優先：口座振替のお知らせは他のカテゴリより先にチェックし、
      # 専用リストに入れる（銀行・支払いには入れず二重に出さない）。
      if any(_normalize(kw) in haystack for kw in DIRECT_DEBIT_KEYWORDS):
        if len(direct_debit_mail) < 5:
          direct_debit_mail.append({
            "id": message['id'],
            "subject": subject,
            "from": sender,
            "date": date_str,
            "snippet": snippet,
          })
        continue

      # 新機能の宣伝・お知らせ系のメールは、キーワードに当てはまっても除外する。
      if any(_normalize(marker) in haystack for marker in PROMOTIONAL_MARKERS):
        continue

      matched_label = None
      for category in MAIL_CATEGORIES:
        if any(_normalize(kw) in haystack for kw in category["keywords"]):
          matched_label = category["label"]
          break
      if matched_label is None:
        continue

      # 発送・配達は個別に出さず、「発送済み」と「お届け完了」の件数だけ数える。
      if matched_label == "発送・配達":
        if any(_normalize(kw) in haystack for kw in DELIVERED_KEYWORDS):
          delivered_count += 1
        else:
          shipped_count += 1
        continue

      if len(payment_mail) < 8:
        payment_mail.append({
          "id": message['id'],
          "subject": subject,
          "from": sender,
          "date": date_str,
          "snippet": snippet,
          "category": matched_label
        })

    return jsonify({
      "calendar": formatted_events,
      "deadlines": deadlines,
      "yesterday_date_label": _format_date_label(yesterday_date),
      "yesterday_events": yesterday_events,
      "payment_mail": payment_mail,
      "direct_debit_mail": direct_debit_mail,
      "shipped_count": shipped_count,
      "delivered_count": delivered_count
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
