from flask import Flask, request
import requests
import os
import csv
import random
import hashlib
import hmac
import base64
import re

app = Flask(__name__)

# LINE 設定
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
LINE_REPLY_URL = 'https://api.line.me/v2/bot/message/reply'

# 1. 讀取題庫 (加入選項拆解邏輯)
def load_questions():
    questions = []
    if not os.path.exists('aws_questions.csv'): return []
    try:
        with open('aws_questions.csv', 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                q_text = row.get('題目(中)', '').strip()
                opt_raw = row.get('選項(中)', '').strip()
                ans = row.get('正確答案', 'A').strip().upper()
                explain = row.get('解析(中)', '').strip() or "請參考 AWS 官方文件。"
                
                # 簡單拆解 A. B. C. D. 內容
                opts = {}
                for char in ['A', 'B', 'C', 'D']:
                    pattern = rf"{char}[.)](.*?)(?=[B-D][.)]|$)"
                    match = re.search(pattern, opt_raw, re.DOTALL)
                    opts[char] = match.group(1).strip() if match else f"選項 {char}"

                if q_text:
                    questions.append({'q': q_text, 'opts': opts, 'ans': ans, 'exp': explain})
        return questions
    except: return []

QUESTIONS = load_questions()

# 2. LINE 訊息發送工具
def send_line_message(reply_token, messages):
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'}
    payload = {'replyToken': reply_token, 'messages': messages}
    requests.post(LINE_REPLY_URL, headers=headers, json=payload)

# 3. 歡迎訊息 & 證照選單 (Template Message)
def get_welcome_menu():
    return [{
        "type": "template",
        "altText": "歡迎使用 AWS 題庫助手",
        "template": {
            "type": "buttons",
            "title": "AWS 證照練習助手",
            "text": "妳好！我可以陪妳練習 SAA 或 SAP 考題。請點擊下方開始：",
            "actions": [
                {"type": "postback", "label": "開始練習 SAA", "data": "action=start_saa"},
                {"type": "postback", "label": "開始練習 SAP", "data": "action=start_sap"}
            ]
        }
    }]

# 4. 出題按鈕格式
def get_question_template(q_index):
    q = QUESTIONS[q_index]
    return [{
        "type": "template",
        "altText": "新題目來了",
        "template": {
            "type": "buttons",
            "title": f"考題 (編號 {q_index+1})",
            "text": (q['q'][:150] + '...') if len(q['q']) > 150 else q['q'],
            "actions": [
                {"type": "postback", "label": f"A. {q['opts']['A'][:15]}", "data": f"action=ans&user=A&correct={q['ans']}&idx={q_index}"},
                {"type": "postback", "label": f"B. {q['opts']['B'][:15]}", "data": f"action=ans&user=B&correct={q['ans']}&idx={q_index}"},
                {"type": "postback", "label": f"C. {q['opts']['C'][:15]}", "data": f"action=ans&user=C&correct={q['ans']}&idx={q_index}"},
                {"type": "postback", "label": f"D. {q['opts']['D'][:15]}", "data": f"action=ans&user=D&correct={q['ans']}&idx={q_index}"}
            ]
        }
    }]

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_data(as_text=True)
    events = request.json.get('events', [])
    for event in events:
        # A. 處理加好友 (Follow)
        if event['type'] == 'follow':
            send_line_message(event['replyToken'], get_welcome_menu())
        
        # B. 處理按鈕點擊 (Postback)
        elif event['type'] == 'postback':
            data = event['postback']['data']
            
            # 使用者點擊「開始練習」
            if "action=start_saa" in data:
                idx = random.randint(0, len(QUESTIONS)-1)
                send_line_message(event['replyToken'], get_question_template(idx))
            
            # 使用者點擊「答案按鈕」
            elif "action=ans" in data:
                # 解析隱藏數據
                params = dict(item.split('=') for item in data.split('&'))
                user_ans = params['user']
                correct_ans = params['correct']
                q_idx = int(params['idx'])
                
                result_text = "🎉 答對了！" if user_ans == correct_ans else f"❌ 答錯了，正確答案是 {correct_ans}"
                explain_text = f"{result_text}\n\n💡 解析：\n{QUESTIONS[q_idx]['exp']}"
                
                # 回傳解析，並附帶一個「下一題」按鈕
                next_menu = [
                    {"type": "text", "text": explain_text},
                    {
                        "type": "template",
                        "altText": "下一步",
                        "template": {
                            "type": "buttons",
                            "text": "準備好挑戰下一題了嗎？",
                            "actions": [{"type": "postback", "label": "下一題", "data": "action=start_saa"}]
                        }
                    }
                ]
                send_line_message(event['replyToken'], next_menu)
                
        # C. 處理一般文字訊息 (如果使用者還是硬要打字)
        elif event['type'] == 'message':
            send_line_message(event['replyToken'], get_welcome_menu())

    return 'OK'

@app.route("/")
def home(): return "AWS Bot is running"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
