from flask import Flask, request, jsonify
import requests
import os
import csv
import random
import hashlib
import hmac
import base64

app = Flask(__name__)

# LINE 設定
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN', 'YOUR_TOKEN_HERE')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET', 'YOUR_SECRET_HERE')
LINE_API = 'https://api.line.me/v2/bot/message/reply'

# 從 CSV 載入題庫
def load_questions_from_csv():
    """從 CSV 載入題庫"""
    questions = []
    
    try:
        if not os.path.exists('aws_questions.csv'):
            print("⚠️ CSV 檔案不存在，使用預設題庫")
            return get_default_questions()
        
        with open('aws_questions.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                question_text = row.get('中文翻譯', '').strip()
                
                if not question_text or len(question_text) < 10:
                    continue
                
                # 解析題目和選項
                lines = question_text.split('\n')
                question_main = []
                options = {}
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('A.') or line.startswith('A)'):
                        options['A'] = line[2:].strip()
                    elif line.startswith('B.') or line.startswith('B)'):
                        options['B'] = line[2:].strip()
                    elif line.startswith('C.') or line.startswith('C)'):
                        options['C'] = line[2:].strip()
                    elif line.startswith('D.') or line.startswith('D)'):
                        options['D'] = line[2:].strip()
                    elif line and not any(line.startswith(x) for x in ['A.', 'B.', 'C.', 'D.', 'A)', 'B)', 'C)', 'D)']):
                        question_main.append(line)
                
                if len(options) >= 4:
                    questions.append({
                        'q': '\n'.join(question_main) if question_main else question_text[:200],
                        'options': options,
                        'correct': row.get('社群答案', row.get('正確答案', 'A')).strip().upper(),
                        'explain': f"正確答案：{row.get('社群答案', 'A')}"
                    })
        
        print(f"✅ 成功從 CSV 載入 {len(questions)} 題")
        
        if len(questions) == 0:
            return get_default_questions()
        
        return questions
        
    except Exception as e:
        print(f"❌ 載入 CSV 失敗：{e}")
        return get_default_questions()

def get_default_questions():
    """預設題庫"""
    return [
        {
            'q': '某公司需要在AWS上部署一個需要處理突發流量的網站，但預算有限。以下哪種EC2購買選項最適合？',
            'options': {
                'A': 'On-Demand Instances',
                'B': 'Reserved Instances',
                'C': 'Spot Instances',
                'D': 'Savings Plans'
            },
            'correct': 'C',
            'explain': 'Spot Instances 可以以更低的價格使用未使用的 EC2 容量，最適合突發流量且預算有限的場景。'
        },
        {
            'q': '企業應用程序需要共享文件系統，可以同時被多個EC2實例訪問和修改。以下哪個AWS服務最適合？',
            'options': {
                'A': 'Amazon S3',
                'B': 'Amazon EBS',
                'C': 'Amazon EFS',
                'D': 'AWS Storage Gateway'
            },
            'correct': 'C',
            'explain': 'Amazon EFS 提供完全託管的共享文件系統，支援多個 EC2 實例同時讀寫。'
        },
        {
            'q': '公司要求所有存儲在S3的數據必須加密，且加密金鑰必須由公司自行管理。應該使用什麼加密方式？',
            'options': {
                'A': 'S3默認加密',
                'B': 'SSE-S3',
                'C': 'SSE-KMS',
                'D': 'SSE-C'
            },
            'correct': 'C',
            'explain': 'SSE-KMS 允許公司通過 AWS KMS 管理加密金鑰，提供金鑰使用的審計日誌。'
        }
    ]

# 載入題庫
QUESTIONS = load_questions_from_csv()
print(f"📚 題庫已載入，共 {len(QUESTIONS)} 題")

# 儲存用戶狀態
users = {}

def verify_signature(body, signature):
    """驗證 LINE 簽名"""
    hash_value = hmac.new(
        CHANNEL_SECRET.encode('utf-8'),
        body.encode('utf-8'),
        hashlib.sha256
    ).digest()
    expected_signature = base64.b64encode(hash_value).decode('utf-8')
    return signature == expected_signature

def send_reply(reply_token, text):
    """發送回覆訊息"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    
    data = {
        'replyToken': reply_token,
        'messages': [
            {
                'type': 'text',
                'text': text
            }
        ]
    }
    
    response = requests.post(LINE_API, headers=headers, json=data)
    return response.status_code == 200

@app.route("/")
def home():
    return f"✅ AWS LINE Bot is running! 題庫共 {len(QUESTIONS)} 題"

@app.route("/callback", methods=['POST'])
def callback():
    # 驗證簽名
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    
    if not verify_signature(body, signature):
        print("❌ Invalid signature")
        return 'Invalid signature', 400
    
    # 解析事件
    try:
        events = request.json.get('events', [])
        
        for event in events:
            if event['type'] == 'message' and event['message']['type'] == 'text':
                handle_message(event)
        
        return 'OK', 200
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 'Error', 500

def handle_message(event):
    """處理訊息"""
    user_id = event['source']['userId']
    text = event['message']['text'].strip()
    reply_token = event['replyToken']
    
    # 初始化用戶
    if user_id not in users:
        users[user_id] = {'asked': [], 'score': 0, 'total': 0}
    
    # 開始測驗
    if '開始' in text or 'start' in text.lower() or '重新' in text:
        users[user_id] = {'asked': [], 'score': 0, 'total': 0}
        
        # 隨機選一題
        q = random.choice(QUESTIONS)
        users[user_id]['current_q'] = q
        users[user_id]['asked'].append(QUESTIONS.index(q))
        
        # 格式化選項
        options_text = '\n'.join([f"{k}. {v}" for k, v in q['options'].items()])
        msg = f"🎓 AWS SAA 測驗開始！\n\n【第 1 題】\n\n{q['q']}\n\n{options_text}\n\n請輸入答案 (A/B/C/D)"
        
        send_reply(reply_token, msg)
        return
    
    # 回答問題
    if text.upper() in ['A', 'B', 'C', 'D']:
        if 'current_q' not in users[user_id]:
            send_reply(reply_token, '請先輸入「開始」開始測驗')
            return
        
        q = users[user_id]['current_q']
        users[user_id]['total'] += 1
        
        correct = (text.upper() == q['correct'])
        
        if correct:
            users[user_id]['score'] += 1
            result = f"✅ 答對了！\n\n💡 {q['explain']}"
        else:
            result = f"❌ 答錯了！\n正確答案：{q['correct']}\n\n💡 {q['explain']}"
        
        result += f"\n\n📊 目前成績：{users[user_id]['score']}/{users[user_id]['total']}"
        
        # 選下一題
        available = [i for i in range(len(QUESTIONS)) if i not in users[user_id]['asked']]
        
        if len(available) > 0 and users[user_id]['total'] < 10:
            next_q = QUESTIONS[random.choice(available)]
            users[user_id]['current_q'] = next_q
            users[user_id]['asked'].append(QUESTIONS.index(next_q))
            
            options_text = '\n'.join([f"{k}. {v}" for k, v in next_q['options'].items()])
            msg = f"{result}\n\n{'='*30}\n\n【第 {users[user_id]['total']+1} 題】\n\n{next_q['q']}\n\n{options_text}\n\n請輸入答案"
        else:
            score = users[user_id]['score']
            total = users[user_id]['total']
            pct = int(score * 100 / total) if total > 0 else 0
            
            if pct >= 80:
                emoji = "🏆"
                comment = "優秀！"
            elif pct >= 60:
                emoji = "💪"
                comment = "不錯！"
            else:
                emoji = "📚"
                comment = "繼續加油！"
            
            msg = f"{result}\n\n{'='*30}\n\n{emoji} 測驗完成！\n\n最終得分：{score}/{total} ({pct}%)\n{comment}\n\n輸入「開始」重新測驗"
        
        send_reply(reply_token, msg)
    else:
        send_reply(reply_token, '💡 請輸入「開始」開始測驗，或輸入 A/B/C/D 回答問題')

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
