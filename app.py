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

# 🎨 莫蘭迪色系配置 (Morandi Palette)
COLOR_PRIMARY = "#95A3A4"   # 莫蘭迪綠 (主按鈕)
COLOR_SECONDARY = "#B8A99A" # 莫蘭迪砂 (次按鈕)
COLOR_TEXT_MAIN = "#555555" # 深灰 (內文)
COLOR_TEXT_SOFT = "#7E8989" # 煙燻灰 (標題)

# 全域題庫
QUESTIONS = {'SAA': [], 'SAP': []}

def load_questions_from_excel():
    filename = 'AWS_SAA_SAP_繁體中文版.xlsx'
    if not os.path.exists(filename):
        print("⚠️ 找不到 Excel 檔案")
        return "找不到檔案"

    try:
        wb = openpyxl.load_workbook(filename, data_only=True)
        for category in ['SAA', 'SAP']:
            if category in wb.sheetnames:
                sheet = wb[category]
                headers = [str(cell.value).strip() if cell.value else "" for cell in sheet[1]]
                col_map = {name: i for i, name in enumerate(headers) if name}
                
                # 檢查必要欄位是否存在 (相容多種命名方式)
                q_col = col_map.get('題目(中)')
                opt_col = col_map.get('選項(中)')
                ans_col = col_map.get('正確答案')
                exp_col = col_map.get('解析(中)') or col_map.get('專業解析')
                
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    if row[q_col] and row[opt_col]: # 確保題目跟選項都有內容才加入
                        q_data = {
                            'q': str(row[q_col]).strip(),
                            'opts_raw': str(row[opt_col]).strip(),
                            'ans': str(row[ans_col] or "A").strip().upper(),
                            'exp': str(row[exp_col] or "暫無詳細解析。").strip()
                        }
                        q_data['opts'] = parse_options(q_data['opts_raw'])
                        QUESTIONS[category].append(q_data)
        return "成功"
    except Exception as e:
        return str(e)

def parse_options(raw_text):
    opts = {}
    for char in ['A', 'B', 'C', 'D']:
        # 同時支援 A. B. 或 A) B) 格式
        pattern = rf"{char}[.)](.*?)(?=[A-D][.)]|$)"
        match = re.search(pattern, raw_text, re.DOTALL)
        opts[char] = match.group(1).strip() if match else ""
    return opts

# 啟動時載入
load_status = load_questions_from_excel()

def send_line(reply_token, messages):
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'}
    payload = {'replyToken': reply_token, 'messages': messages}
    requests.post(LINE_REPLY_URL, headers=headers, json=payload)

# --- UI 介面 ---

def welcome_flex():
    return {
        "type": "flex", "altText": "AWS 學習助手",
        "contents": {
            "type": "bubble",
            "header": { "type": "box", "layout": "vertical", "contents": [{ "type": "text", "text": "AWS CERTIFIED GUIDE", "weight": "bold", "color": COLOR_TEXT_SOFT, "size": "sm", "letterSpacing": "0.1k" }] },
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": "妳好！今天要練習哪一科？", "weight": "bold", "size": "lg", "color": COLOR_TEXT_MAIN },
                { "type": "text", "text": "💡 點擊下方按鈕開始隨機出題，祝妳順利考取證照！", "wrap": True, "size": "xs", "color": "#999999", "margin": "md" }
            ]},
            "footer": { "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "action": { "type": "postback", "label": "SAA (助理架構師)", "data": "type=SAA" } },
                { "type": "button", "style": "primary", "color": COLOR_SECONDARY, "action": { "type": "postback", "label": "SAP (專業架構師)", "data": "type=SAP" } }
            ]}
        }
    }

def question_flex(category, idx):
    q = QUESTIONS[category][idx]
    option_texts = []
    for char in ['A', 'B', 'C', 'D']:
        if q['opts'].get(char):
            option_texts.append({ "type": "text", "text": f"{char}. {q['opts'][char]}", "wrap": True, "size": "sm", "margin": "md", "color": "#666666" })

    return {
        "type": "flex", "altText": "新題目",
        "contents": {
            "type": "bubble",
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": f"AWS {category} PRACTICE", "size": "xs", "color": COLOR_PRIMARY, "weight": "bold" },
                { "type": "text", "text": q['q'], "wrap": True, "weight": "bold", "margin": "md", "size": "md", "color": COLOR_TEXT_MAIN },
                { "type": "separator", "margin": "xl" },
                { "type": "box", "layout": "vertical", "margin": "lg", "contents": option_texts }
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
        reply_token = event['replyToken']
        
        # 處理追蹤或輸入文字 (叫出主選單)
        if event['type'] == 'follow' or (event['type'] == 'message' and event['message']['type'] == 'text'):
            if load_status != "成功":
                send_line(reply_token, [{"type": "text", "text": f"❌ 系統錯誤：{load_status}"}])
            else:
                send_line(reply_token, [welcome_flex()])
            
        elif event['type'] == 'postback':
            data = parse_qs(event['postback']['data'])
            
            # 1. 抽題邏輯
            if 'type' in data:
                cat = data['type'][0]
                if not QUESTIONS[cat]:
                    send_line(reply_token, [{"type": "text", "text": f"目前 {cat} 題庫中還沒有中文題目喔！"}])
                else:
                    idx = random.randint(0, len(QUESTIONS[cat])-1)
                    send_line(reply_token, [question_flex(cat, idx)])
            
            # 2. 答題判定 + 解析 + 選擇按鈕
            elif 'ans' in data:
                user_ans, correct_ans, cat, q_idx = data['ans'][0], data['c'][0], data['t'][0], int(data['id'][0])
                explain = QUESTIONS[cat][q_idx]['exp']
                
                # 判定對錯
                title = "🎉 答對了！" if user_ans == correct_ans else f"❌ 答錯了，正解是 {correct_ans}"
                
                # 組合訊息：解析文字 + 下一步按鈕卡片
                send_line(reply_token, [
                    { "type": "text", "text": f"{title}\n\n💡 解析：\n{explain}" },
                    {
                        "type": "flex", "altText": "下一步",
                        "contents": {
                            "type": "bubble", "size": "small",
                            "body": { "type": "box", "layout": "vertical", "spacing": "md", "contents": [
                                { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "action": { "type": "postback", "label": "挑戰下一題", "data": f"type={cat}" } },
                                { "type": "button", "style": "secondary", "action": { "type": "postback", "label": "回主選單", "data": "main=1" } }
                            ]}
                        }
                    }
                ])
                
            # 3. 回主選單
            elif 'main' in data:
                send_line(reply_token, [welcome_flex()])
                
    return 'OK'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
