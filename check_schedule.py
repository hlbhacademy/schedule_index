import pandas as pd
import sys

SCHEDULE_FILE = 'schedule.xlsx'

def main():
    # 嘗試讀檔
    try:
        df = pd.read_excel(SCHEDULE_FILE, header=None)
    except Exception as e:
        print(f"❌ 無法讀取 {SCHEDULE_FILE}：{e}")
        sys.exit(1)

    # 自動偵測表頭起始位置（假設「班級」二字出現在標題）
    header_row = None
    for i, row in df.iterrows():
        if row.astype(str).str.contains('班級').any():
            header_row = i
            break
    if header_row is None:
        print("❌ 找不到『班級』表頭，檔案格式有誤！")
        sys.exit(1)

    # 讀取正確資料
    df = pd.read_excel(SCHEDULE_FILE, header=header_row)
    df = df.dropna(how='all')  # 移除全空白行

    # 必要欄位檢查
    required_columns = ['班級', '星期', '節次', '科目', '教師']
    for col in required_columns:
        if col not in df.columns:
            print(f"❌ 缺少必要欄位：{col}")
            sys.exit(1)

    # 逐行檢查資料完整性
    errors = []
    for idx, row in df.iterrows():
        for col in required_columns:
            val = row[col]
            if pd.isna(val):
                # 「空白」可接受，視為無異動
                continue
            # 可加入額外格式驗證，例如班級、星期、節次必須有特定格式
            if col == '星期':
                try:
                    x = int(val)
                    if not 1 <= x <= 7:
                        errors.append(f"第{idx+1}行『星期』欄有非法數字：{val}")
                except:
                    errors.append(f"第{idx+1}行『星期』欄格式錯誤：{val}")
            if col == '節次':
                try:
                    y = int(val)
                    if not 1 <= y <= 8:
                        errors.append(f"第{idx+1}行『節次』欄有非法數字：{val}")
                except:
                    errors.append(f"第{idx+1}行『節次』欄格式錯誤：{val}")

    if errors:
        print("❌ 檢查發現以下錯誤：")
        for err in errors:
            print(err)
        print("請檢查原始檔案內容，修正後再嘗試。")
        sys.exit(1)
    else:
        print("✅ 格式檢查通過，可用於後續課表系統。")
        # 如果需要，可將乾淨資料另存成 json/csv 給下游
        df.to_csv('schedule_checked.csv', index=False, encoding='utf-8-sig')
        print("已將乾淨資料存為 schedule_checked.csv。")

if __name__ == '__main__':
    main()
