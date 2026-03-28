from flask import Flask, request
import requests
import os
import random
import re
import openpyxl
from urllib.parse import parse_qs

app = Flask(__name__)

# LINE 設定
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
LINE_REPLY_URL = 'https://api.line.me/v2/bot/message/reply'

# 🎨 莫蘭迪色系配置
COLOR_PRIMARY = "#95A3A4"   # 莫蘭迪綠 (主視覺)
COLOR_SECONDARY = "#B8A99A" # 莫蘭迪砂 (副視覺)
COLOR_TEXT_SOFT = "#7E8989" # 煙燻深綠 (標題)
COLOR_BG_LIGHT = "#E2E2E2"  # 極淺灰 (分隔線)

# 全域題庫儲存
QUESTIONS = {'SAA': [], 'SAP': []}

def load_questions_from_excel():
    filename = 'AWS_SAA_SAP_繁體中文版.xlsx'
    if not os.path.exists(filename):
        print("⚠️ 找不到 Excel 檔案")
        return

    wb = openpyxl.load_workbook(filename, data_only=True)
    for category in ['SAA', 'SAP']:
        if category in wb.sheetnames:
            sheet = wb[category]
            # 取得標題列並建立索引對照
            headers = [cell.value for cell in sheet[1]]
            col_map = {name: i for i, name in enumerate(headers) if name}
            
            for row in sheet.iter_rows(min_row=2, values_only=True):
                # 確保題目不為空才加入
                q_text = row[col_map.get('題目(中)', 0)]
                if q_text:
                    q_data = {
                        'q': str(q_text).strip(),
                        'opts_raw': str(row[col_map.get('選項(中)', 0)]).strip(),
                        'ans': str(row[col_map.get('正確答案', 0)]).strip().upper(),
                        'exp': str(row[col_map.get('解析(中)', 0)] or "暫無詳細解析。").strip()
                    }
                    # 拆解 A. B. C. D.
                    q_data['opts'] = parse_options(q_data['opts_raw'])
                    QUESTIONS[category].append(q_data)
    print(f"✅ 載入完成: SAA({len(QUESTIONS['SAA'])}) SAP({len(QUESTIONS['SAP'])})")

def parse_options(raw_text):
    opts = {}
    for char in ['A', 'B', 'C', 'D']:
        pattern = rf"{char}[.)](.*?)(?=[A-D][.)]|$)"
        match = re.search(pattern, raw_text, re.DOTALL)
        opts[char] = match.group(1).strip() if match else f"選項 {char}"
    return opts

load_questions_from_excel()

def send_line(reply_token, messages):
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'}
    payload = {'replyToken': reply_token, 'messages': messages}
    requests.post(LINE_REPLY_URL, headers=headers, json=payload)

# --- Flex Message UI 莫蘭迪風格設計 ---

def welcome_flex():
    return {
        "type": "flex", "altText": "AWS 學習助手",
        "contents": {
            "type": "bubble",
            "header": { "type": "box", "layout": "vertical", "contents": [{ "type": "text", "text": "AWS EXAM GUIDE", "weight": "bold", "color": COLOR_TEXT_SOFT, "size": "sm", "letterSpacing": "0.1k" }] },
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": "妳好！準備好要挑戰了嗎？", "weight": "bold", "size": "lg", "color": "#555555" },
                { "type": "text", "text": "💡 選擇下方證照類別開始練習，所有進度將會隨機出題。", "wrap": True, "size": "xs", "color": "#999999", "margin": "md" }
            ]},
            "footer": { "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "action": { "type": "postback", "label": "SAA (助理架構師)", "data": "type=SAA" } },
                { "type": "button", "style": "primary", "color": COLOR_SECONDARY, "action": { "type": "postback", "label": "SAP (專業架構師)", "data": "type=SAP" } }
            ]}
        }
    }

def question_flex(category, idx):
    q = QUESTIONS[category][idx]
    option_blocks = []
    for char in ['A', 'B', 'C', 'D']:
        option_blocks.append({ "type": "text", "text": f"{char}. {q['opts'][char]}", "wrap": True, "size": "sm", "margin": "md", "color": "#666666" })

    return {
        "type": "flex", "altText": "新題目",
        "contents": {
            "type": "bubble",
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": f"AWS {category} PRACTICE", "size": "xs", "color": COLOR_PRIMARY, "weight": "bold" },
                { "type": "text", "text": q['q'], "wrap": True, "weight": "bold", "margin": "md", "size": "md", "color": "#444444" },
                { "type": "box", "layout": "vertical", "margin": "lg", "contents": option_blocks }
            ]},
            "footer": { "type": "box", "layout": "vertical", "contents": [
                { "type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "height": "sm", "action": { "type": "postback", "label": "A", "data": f"ans=A&c={q['ans']}&id={idx}&t={category}" } },
                    { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "height": "sm", "action": { "type": "postback", "label": "B", "data": f"ans=B&c={q['ans']}&id={idx}&t={category}" } },
                    { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "height": "sm", "action": { "type": "postback", "label": "C", "data": f"ans=C&c={q['ans']}&id={idx}&t={category}" } },
                    { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "height": "sm", "action": { "type": "postback", "label": "D", "data": f"ans=D&c={q['ans']}&id={idx}&t={category}" } }
                ]}
            ]}
        }
    }

@app.route("/callback", methods=['POST'])
def callback():
    events = request.json.get('events', [])
    for event in events:
        if event['type'] == 'message':
            send_line(event['replyToken'], [welcome_flex()])
        elif event['type'] == 'postback':
            data = parse_qs(event['postback']['data'])
            
            if 'type' in data: # 選擇考科或下一題
                cat = data['type'][0]
                idx = random.randint(0, len(QUESTIONS[cat])-1)
                send_line(event['replyToken'], [question_flex(cat, idx)])
                
            elif 'ans' in data: # 判斷答案
                user_ans = data['ans'][0]
                correct_ans = data['c'][0]
                cat = data['t'][0]
                q_idx = int(data['id'][0])
                explain = QUESTIONS[cat][q_idx]['exp']
                
                res_text = "🎉 答對了！" if user_ans == correct_ans else f"❌ 答錯了，正解是 {correct_ans}"
                
                send_line(event['replyToken'], [
                    { "type": "text", "text": f"{res_text}\n\n💡 解析：\n{explain}" },
                    { "type": "flex", "altText": "選單", "contents": {
                        "type": "bubble", "size": "small", "body": { "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                            { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "action": { "type": "postback", "label": "下一題", "data": f"type={cat}" } },
                            { "type": "button", "style": "secondary", "action": { "type": "postback", "label": "回主選單", "data": "main=1" } }
                        ]}}
                    }
                ])
            elif 'main' in data:
                send_line(event['replyToken'], [welcome_flex()])
    return 'OK'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
