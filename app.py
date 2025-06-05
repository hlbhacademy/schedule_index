from flask import Flask, render_template, request, jsonify
import pandas as pd

app = Flask(__name__)

SPECIAL_ROOMS = [
    "健康與護理教室", "分組活動教室", "原住民資源教室", "美術教室", "自然科學教室", "行銷生涯教室",
    "語言教室B", "語言教室C", "門市情境學科教室", "門市服務教室",
    "電腦教室202", "電腦教室203", "電腦教室301", "電腦教室302", "電腦教室303",
    "電腦教室401", "電腦教室402", "電腦教室403"
]
FORBIDDEN_SUBJECTS = ["團體活動時間", "多元選修", "彈性學習時間", "本土語文"]

def load_schedule():
    try:
        df = pd.read_excel('schedule.xlsx', engine='openpyxl')
    except Exception as e:
        print("載入檔案錯誤：", e)
        return None
    df = df.fillna('')
    df = df[
        (df['教師名稱'] != '') &
        (df['班級名稱'] != '') &
        (df['科目名稱'] != '') &
        (df['節次'] != '') &
        (df['星期'] != '')
    ].copy()
    df['星期'] = df['星期'].astype(int)
    df['節次'] = df['節次'].astype(int)
    return df

def get_sorted_classes(classes):
    pri = ["英", "會", "商", "資", "多"]
    result = []
    for key in pri:
        result.extend(sorted([c for c in classes if c.startswith(key)]))
    others = sorted([c for c in classes if c not in result])
    return result + others

def get_sorted_teachers(teachers):
    def strokes(name):
        ch = name[0]
        strokes_dict = {
            "丁": 2, "王": 4, "朱": 6, "林": 8, "洪": 9, "周": 8, "李": 7, "楊": 13, "粘": 11,
            "許": 11, "陳": 16, "蔡": 17, "黃": 12, "張": 11, "江": 6, "莊": 10, "龔": 22,
        }
        return strokes_dict.get(ch, ord(ch))
    return sorted(teachers, key=lambda n: strokes(n))

def get_sorted_rooms(rooms):
    special = [r for r in rooms if r in SPECIAL_ROOMS]
    general = [r for r in rooms if r not in SPECIAL_ROOMS]
    return special + sorted(general)

@app.route('/')
def index():
    df = load_schedule()
    if df is None or df.empty:
        return '<h1 style="margin:100px;text-align:center;">系統異常或查無資料，請稍後再試！</h1>'
    class_names = get_sorted_classes(df['班級名稱'].unique())
    teacher_names = get_sorted_teachers(df['教師名稱'].unique())
    room_names = get_sorted_rooms(df['教室名稱'].unique())
    weekday_dates = {}
    for i, row in df.drop_duplicates(['星期']).iterrows():
        weekday_dates[row['星期']] = row['日期']
    return render_template('index.html',
        classes=class_names,
        teachers=teacher_names,
        rooms=room_names,
        default_mode='班級',
        default_class=class_names[0] if class_names else '',
        weekday_dates=weekday_dates
    )

@app.route('/api/schedule', methods=['POST'])
def api_schedule():
    mode = request.form.get('mode')
    value = request.form.get('value')
    df = load_schedule()
    if df is None or df.empty:
        return jsonify({'status': 'error', 'html': ''})
    weekday_dates = {}
    for i, row in df.drop_duplicates(['星期']).iterrows():
        weekday_dates[row['星期']] = row['日期']
    # 這裡做重點修正！根據查詢模式過濾
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

if __name__ == '__main__':
    app.run(debug=True)
