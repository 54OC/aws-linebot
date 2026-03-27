from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('CHANNEL_SECRET'))

# 簡單的題庫（先用硬編碼測試）
QUESTIONS = {
    'SAA': [
        {
            'q': '某公司需要在AWS上部署一個需要處理突發流量的網站，但預算有限。以下哪種EC2購買選項最適合？',
            'a': 'A. On-Demand\nB. Reserved\nC. Spot Instances\nD. Savings Plans',
            'correct': 'C',
            'explain': 'Spot Instances 最便宜，適合突發流量'
        },
        {
            'q': '企業應用程序需要共享文件系統，可以同時被多個EC2實例訪問。最適合的服務是？',
            'a': 'A. S3\nB. EBS\nC. EFS\nD. Storage Gateway',
            'correct': 'C',
            'explain': 'EFS 支援多個 EC2 同時讀寫'
        }
    ]
}

users = {}

@app.route("/")
def home():
    return "Bot is running!"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text
    
    # 初始化用戶
    if user_id not in users:
        users[user_id] = {'index': 0, 'score': 0}
    
    # 開始測驗
    if '開始' in text or 'start' in text.lower():
        users[user_id] = {'index': 0, 'score': 0}
        q = QUESTIONS['SAA'][0]
        msg = f"第 1 題：\n\n{q['q']}\n\n{q['a']}\n\n請輸入答案（A/B/C/D）"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        return
    
    # 檢查答案
    if text.upper() in ['A', 'B', 'C', 'D']:
        idx = users[user_id]['index']
        if idx >= len(QUESTIONS['SAA']):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='測驗已結束！輸入「開始」重新開始'))
            return
        
        q = QUESTIONS['SAA'][idx]
        
        if text.upper() == q['correct']:
            users[user_id]['score'] += 1
            result = f"✅ 正確！\n\n{q['explain']}\n\n目前得分：{users[user_id]['score']}/{idx+1}"
        else:
            result = f"❌ 錯誤！正確答案是 {q['correct']}\n\n{q['explain']}\n\n目前得分：{users[user_id]['score']}/{idx+1}"
        
        users[user_id]['index'] += 1
        
        # 下一題
        if users[user_id]['index'] < len(QUESTIONS['SAA']):
            next_q = QUESTIONS['SAA'][users[user_id]['index']]
            msg = f"{result}\n\n{'='*20}\n第 {users[user_id]['index']+1} 題：\n\n{next_q['q']}\n\n{next_q['a']}\n\n請輸入答案"
        else:
            total = len(QUESTIONS['SAA'])
            score = users[user_id]['score']
            msg = f"{result}\n\n{'='*20}\n🎉 測驗完成！\n\n最終得分：{score}/{total} ({score*100//total}%)\n\n輸入「開始」重新測驗"
        
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請輸入「開始」開始測驗'))

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
