from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import pandas as pd
import os
from authlib.integrations.flask_client import OAuth
from functools import wraps
from dotenv import load_dotenv

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from apscheduler.schedulers.background import BackgroundScheduler
import io
from googleapiclient.http import MediaIoBaseDownload

# === 讀取環境變數 ===
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecretkey")

# ========== Google OAuth 登入 ==========
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ["GOOGLE_CLIENT_ID"],
    client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
    authorize_params={"hd": "hlbh.hlc.edu.tw"}
)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        if not session["user"]["email"].endswith("@hlbh.hlc.edu.tw"):
            return "無權限，僅限 hlbh.hlc.edu.tw 帳號", 403
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login")
def login():
    return google.authorize_redirect(redirect_uri=url_for("callback", _external=True))

@app.route("/callback")
def callback():
    token = google.authorize_access_token()
    userinfo = google.parse_id_token(token)
    session["user"] = userinfo
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# ========== Google Drive 自動同步 schedule.xlsx ==========
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
SERVICE_ACCOUNT_FILE = 'service_account.json'
FOLDER_ID = "11BU1pxjEWMQJp8vThcC7thp4Mog0YEaJ"  # ←請填入 schedule.xlsx 的 Google Drive 資料夾 ID
FILE_NAME = "schedule.xlsx"

def sync_schedule():
    try:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        drive_service = build('drive', 'v3', credentials=creds)
        query = f"'{FOLDER_ID}' in parents and name='{FILE_NAME}' and trashed=false"
        results = drive_service.files().list(q=query, pageSize=1, fields="files(id, name)").execute()
        items = results.get('files', [])
        if not items:
            print("找不到 schedule.xlsx")
            return
        file_id = items[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.FileIO("schedule.xlsx", "wb")
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.close()
        print("schedule.xlsx 已同步")
    except Exception as e:
        print("同步 schedule.xlsx 發生錯誤:", e)

# 自動每小時同步
scheduler = BackgroundScheduler()
scheduler.add_job(sync_schedule, 'interval', hours=1)
scheduler.start()
# 啟動先同步一次
sync_schedule()

# ========== 課表查詢主程式 ==========
SPECIAL_ROOMS = [
    "健康與護理教室", "分組活動教室", "原住民資源教室", "美術教室", "自然科學教室", "行銷生涯教室",
    "語言教室B", "語言教室C", "門市情境學科教室", "門市服務教室",
    "電腦教室202", "電腦教室203", "電腦教室301", "電腦教室302", "電腦教室303",
    "電腦教室401", "電腦教室402", "電腦教室403"
]
FORBIDDEN_SUBJECTS = ["團體活動時間", "多元選修", "彈性學習時間", "本土語文"]

def load_schedule():
    try:
        return pd.read_excel('schedule.xlsx', engine='openpyxl').fillna('')
    except Exception as e:
        print("課表載入失敗:", e)
        return pd.DataFrame()

@app.route("/")
@login_required
def index():
    user = session.get("user")
    df = load_schedule()
    if df is None or df.empty:
        return '<h1 style="margin:100px;text-align:center;">系統異常或查無資料，請稍後再試！</h1>'
    class_names = sorted(df['班級名稱'].unique())
    teacher_names = sorted(df['教師名稱'].unique())
    room_names = sorted(df['教室名稱'].unique())
    weekday_dates = {}
    for i, row in df.drop_duplicates(['星期']).iterrows():
        weekday_dates[row['星期']] = row['日期']
    return render_template('index.html',
        user=user,
        classes=class_names,
        teachers=teacher_names,
        rooms=room_names,
        default_mode='班級',
        default_class=class_names[0] if class_names else '',
        weekday_dates=weekday_dates
    )

@app.route('/api/schedule', methods=['POST'])
@login_required
def api_schedule():
    mode = request.form.get('mode')
    value = request.form.get('value')
    df = load_schedule()
    if df is None or df.empty:
        return jsonify({'status': 'error', 'html': ''})
    weekday_dates = {}
    for i, row in df.drop_duplicates(['星期']).iterrows():
        weekday_dates[row['星期']] = row['日期']
    if mode == '班級':
        sub_df = df[df['班級名稱'] == value]
    elif mode == '教師':
        sub_df = df[df['教師名稱'] == value]
    elif mode == '教室':
        sub_df = df[df['教室名稱'] == value]
    else:
        sub_df = df.copy()
    table_data = []
    for i, row in sub_df.iterrows():
        table_data.append({
            'weekday': row['星期'],
            'period': row['節次'],
            '班級名稱': row['班級名稱'],
            '教師名稱': row['教師名稱'],
            '科目名稱': row['科目名稱'],
            '教室名稱': row['教室名稱'],
            '日期': row['日期']
        })
    html = render_template('schedule_table.html',
        mode=mode, value=value, table_data=table_data, weekday_dates=weekday_dates)
    return jsonify({'status': 'ok', 'html': html})

@app.route('/api/swap_info', methods=['POST'])
@login_required
def api_swap_info():
    df = load_schedule()
    if df is None or df.empty:
        return jsonify({'status': 'error', 'highlight': {}})
    cls = request.form.get('cls')
    date = request.form.get('date')
    period = int(request.form.get('period'))
    teacher = request.form.get('teacher')
    row = df[(df['班級名稱'] == cls) & (df['日期'] == date) & (df['節次'] == period) & (df['教師名稱'] == teacher)]
    if row.empty:
        return jsonify({'status': 'error', 'highlight': {}})
    w = int(row.iloc[0]['星期'])
    subject = row.iloc[0]['科目名稱']
    room = row.iloc[0]['教室名稱']
    if subject in FORBIDDEN_SUBJECTS:
        return jsonify({'status': 'ok', 'highlight': {}})
    candidates = df[(df['班級名稱'] == cls) & (df['教師名稱'] != teacher)]
    highlight = {}
    for i, r in candidates.iterrows():
        target_teacher = r['教師名稱']
        target_week = r['星期']
        target_period = r['節次']
        target_subject = r['科目名稱']
        target_room = r['教室名稱']
        if target_subject in FORBIDDEN_SUBJECTS:
            continue
        ta = df[(df['教師名稱'] == teacher) & (df['星期'] == target_week) & (df['節次'] == target_period)]
        tb = df[(df['教師名稱'] == target_teacher) & (df['星期'] == w) & (df['節次'] == period)]
        if (ta.empty and tb.empty):
            ok = True
            if room in SPECIAL_ROOMS:
                occupied = df[
                    (df['教室名稱'] == room) &
                    (df['星期'] == target_week) &
                    (df['節次'] == target_period) &
                    (df['班級名稱'] != cls)
                ]
                if not occupied.empty:
                    ok = False
            if target_room in SPECIAL_ROOMS:
                occupied = df[
                    (df['教室名稱'] == target_room) &
                    (df['星期'] == w) &
                    (df['節次'] == period) &
                    (df['班級名稱'] != cls)
                ]
                if not occupied.empty:
                    ok = False
            if ok:
                key = f"{row.iloc[0]['日期']}-{period}"
                highlight[key] = {'type': 'current'}
                tkey = f"{df[df['星期'] == target_week].iloc[0]['日期']}-{target_period}"
                highlight[tkey] = {'type': 'recommended'}
    return jsonify({'status': 'ok', 'highlight': highlight})

if __name__ == "__main__":
    app.run()
