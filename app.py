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
  'カード', 'ご利用', '利用額', '利用料', '料金', '未払', '淧促', '期限',
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
def get_credentials():
  token_json = kv_get('google_oauth_token')
  if not token_json:
    return None
    try:
      info = json.loads(token_json)
      creds = Credentials.from_authorized_user_info(info, SCOPES)
    except Exception:
      return None
      return creds

@app.route('/')
def index():
  return render_template('index.html')

@app.route('/api/status')
def api_status():
  has_credentials = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI)
  return jsonify({"has_credentials": has_credentials})
