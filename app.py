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

# LINE 設定 (由環境變數讀取)
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
LINE_REPLY_URL = 'https://api.line.me/v2/bot/message/reply'

# 1. 讀取題庫 (加強解析邏輯)
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
                explain = row.get('解析(中)', '').strip() or "加油！這題妳一定會。"
                
                # 自動拆解選項 A. B. C. D.
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

# 2. 發送訊息工具
def send_line_message(reply_token, messages):
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'}
    payload = {'replyToken': reply_token, 'messages': messages}
    requests.post(LINE_REPLY_URL, headers=headers, json=payload)

# 3. 歡迎訊息 Flex (加入貼心提示)
def get_welcome_flex():
    return {
        "type": "flex",
        "altText": "歡迎使用 AWS 題庫助手",
        "contents": {
            "type": "bubble",
            "header": { "type": "box", "layout": "vertical", "contents": [{ "type": "text", "text": "AWS 證照練習助手", "weight": "bold", "color": "#E67E22", "size": "lg" }] },
            "body": {
                "type": "box", "layout": "vertical", "contents": [
                    { "type": "text", "text": "妳好！準備好要挑戰了嗎？", "weight": "bold", "size": "md" },
                    { "type": "text", "text": "💡 貼心提醒：由於本機器人部署於免費雲端空間，若一段時間未運行，首次點擊可能會有 15-30 秒的「熱機延遲」。若按鈕沒反應，請稍等片刻或再點擊一次，感謝您的耐心！", "wrap": True, "size": "xs", "color": "#888888", "margin": "md" }
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                    { "type": "button", "style": "primary", "color": "#E67E22", "action": { "type": "postback", "label": "開始練習 SAA", "data": "action=start_saa" } },
                    { "type": "button", "style": "secondary", "action": { "type": "postback", "label": "開始練習 SAP", "data": "action=start_sap" } }
                ]
            }
        }
    }

# 4. 出題卡片 Flex (真．按鈕設計)
def get_question_flex(idx):
    q = QUESTIONS[idx]
    return {
        "type": "flex",
        "altText": "新題目來了",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "contents": [
                    { "type": "text", "text": f"題庫練習 (第 {idx+1} 題)", "size": "xs", "color": "#BCBCBC" },
                    { "type": "text", "text": q['q'], "wrap": True, "weight": "bold", "margin": "md" },
                    { "type": "separator", "margin": "xl" },
                    { "type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
                        { "type": "button", "action": { "type": "postback", "label": f"A. {q['opts']['A'][:18]}", "data": f"action=ans&user=A&correct={q['ans']}&idx={idx}" }, "height": "sm" },
                        { "type": "button", "action": { "type": "postback", "label": f"B. {q['opts']['B'][:18]}", "data": f"action=ans&user=B&correct={q['ans']}&idx={idx}" }, "height": "sm" },
                        { "type": "button", "action": { "type": "postback", "label": f"C. {q['opts']['C'][:18]}", "data": f"action=ans&user=C&correct={q['ans']}&idx={idx}" }, "height": "sm" },
                        { "type": "button", "action": { "type": "postback", "label": f"D. {q['opts']['D'][:18]}", "data": f"action=ans&user=D&correct={q['ans']}&idx={idx}" }, "height": "sm" }
                    ]}
                ]
            }
        }
    }

@app.route("/callback", methods=['POST'])
def callback():
    events = request.json.get('events', [])
    for event in events:
        if event['type'] == 'follow':
            send_line_message(event['replyToken'], [get_welcome_flex()])
        elif event['type'] == 'postback':
            data = event['postback']['data']
            if "action=start" in data:
                idx = random.randint(0, len(QUESTIONS)-1)
                send_line_message(event['replyToken'], [get_question_flex(idx)])
            elif "action=ans" in data:
                params = dict(item.split('=') for item in data.split('&'))
                user_ans, correct_ans, q_idx = params['user'], params['correct'], int(params['idx'])
                res = "🎉 答對了！" if user_ans == correct_ans else f"❌ 答錯了，正解是 {correct_ans}"
                
                # 回傳結果與「下一題」按鈕
                result_msg = [
                    { "type": "text", "text": f"{res}\n\n💡 解析：\n{QUESTIONS[q_idx]['exp']}" },
                    { "type": "flex", "altText": "下一步", "contents": {
                        "type": "bubble", "size": "small", "body": { "type": "box", "layout": "vertical", "contents": [
                            { "type": "button", "style": "primary", "action": { "type": "postback", "label": "下一題", "data": "action=start_saa" } }
                        ]}
                    }}
                ]
                send_line_message(event['replyToken'], result_msg)
        elif event['type'] == 'message':
            send_line_message(event['replyToken'], [get_welcome_flex()])
    return 'OK'

@app.route("/")
def home(): return "AWS Bot is running"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
