from flask import Flask, request
import requests
import os
import csv
import random
import hashlib
import hmac
import base64

app = Flask(__name__)

# LINE 設定 (記得在 Render 的 Environment Variables 設定這些)
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
LINE_API = 'https://api.line.me/v2/bot/message/reply'

def load_questions_from_csv():
    """根據妳提供的 CSV 格式精準讀取"""
    questions = []
    filename = 'aws_questions.csv'
    
    if not os.path.exists(filename):
        print(f"⚠️ 找不到 {filename}")
        return []

    try:
        # 使用 utf-8-sig 讀取，防止 Excel 產生的亂碼
        with open(filename, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                q_text = row.get('題目(中)', '').strip()
                options_raw = row.get('選項(中)', '').strip()
                ans = row.get('正確答案', 'A').strip().upper()
                explain = row.get('解析(中)', '加油！這題妳一定會。').strip()

                if q_text and options_raw:
                    # 簡單處理選項格式
                    questions.append({
                        'q': q_text,
                        'options_text': options_raw,
                        'correct': ans,
                        'explain': explain
                    })
        print(f"✅ 成功載入 {len(questions)} 題")
        return questions
    except Exception as e:
        print(f"❌ 讀取失敗: {e}")
        return []

QUESTIONS = load_questions_from_csv()

def verify_signature(body, signature):
    if not CHANNEL_SECRET: return True # 開發測試用
    hash_value = hmac.new(CHANNEL_SECRET.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).digest()
    return signature == base64.b64encode(hash_value).decode('utf-8')

def send_reply(reply_token, text):
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'}
    data = {'replyToken': reply_token, 'messages': [{'type': 'text', 'text': text}]}
    requests.post(LINE_API, headers=headers, json=data)

@app.route("/")
def home():
    return f"Bot is online. Questions loaded: {len(QUESTIONS)}"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    if not verify_signature(body, signature): return 'Invalid signature', 400
    
    events = request.json.get('events', [])
    for event in events:
        if event['type'] == 'message' and event['message']['type'] == 'text':
            handle_message(event)
    return 'OK'

users = {}

def handle_message(event):
    user_id = event['source']['userId']
    text = event['message']['text'].strip().upper()
    reply_token = event['replyToken']

    if user_id not in users:
        users[user_id] = {'asked': [], 'score': 0, 'total': 0}

    if text in ['開始', 'START', '重新']:
        users[user_id] = {'asked': [], 'score': 0, 'total': 0}
        q = random.choice(QUESTIONS)
        users[user_id]['current_q'] = q
        msg = f"🎓 AWS SAA 測驗開始！\n\n【題目】\n{q['q']}\n\n【選項】\n{q['options_text']}\n\n請輸入答案 (A/B/C/D)"
        send_reply(reply_token, msg)
        
    elif text in ['A', 'B', 'C', 'D']:
        if 'current_q' not in users[user_id]:
            send_reply(reply_token, "請輸入「開始」來啟動練習喔！")
            return
        
        q = users[user_id]['current_q']
        correct = (text == q['correct'])
        users[user_id]['total'] += 1
        
        if correct:
            users[user_id]['score'] += 1
            res = "✅ 答對了！"
        else:
            res = f"❌ 答錯了，正確答案是 {q['correct']}"
        
        msg = f"{res}\n\n💡 解析：\n{q['explain']}\n\n📊 目前成績：{users[user_id]['score']}/{users[user_id]['total']}\n\n輸入「開始」挑戰下一題！"
        send_reply(reply_token, msg)
    else:
        send_reply(reply_token, "請輸入 A、B、C 或 D 來回答，或輸入「開始」重新練習。")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
