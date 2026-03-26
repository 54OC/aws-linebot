from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    PostbackEvent, TemplateSendMessage, ButtonsTemplate,
    PostbackAction, MessageAction
)
import csv
import os
import random

app = Flask(__name__)

# LINE Bot 設定
line_bot_api = LineBotApi(os.environ.get('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('CHANNEL_SECRET'))

# 從 CSV 載入題庫
def load_questions_from_csv(csv_file='aws_questions.csv'):
    """從 CSV 檔案載入題庫"""
    questions = {'SAA': [], 'SAP': []}
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            saa_count = 0
            
            for row in reader:
                # 從您的 CSV 提取資料
                question_text = row.get('中文翻譯', '').strip()
                
                if not question_text:
                    continue
                
                # 解析選項（從中文翻譯中提取）
                options = {}
                lines = question_text.split('\n')
                question_main = []
                
                for line in lines:
                    line = line.strip()
                    # 檢查是否是選項
                    if line.startswith('A.') or line.startswith('A)'):
                        options['A'] = line[2:].strip()
                    elif line.startswith('B.') or line.startswith('B)'):
                        options['B'] = line[2:].strip()
                    elif line.startswith('C.') or line.startswith('C)'):
                        options['C'] = line[2:].strip()
                    elif line.startswith('D.') or line.startswith('D)'):
                        options['D'] = line[2:].strip()
                    elif not any(line.startswith(x) for x in ['A.', 'B.', 'C.', 'D.', 'A)', 'B)', 'C)', 'D)']):
                        if line:
                            question_main.append(line)
                
                # 如果沒有找到選項，嘗試其他方式
                if not options:
                    options = {
                        'A': '選項 A',
                        'B': '選項 B', 
                        'C': '選項 C',
                        'D': '選項 D'
                    }
                
                question_data = {
                    'id': saa_count,
                    'question': '\n'.join(question_main) if question_main else question_text[:200],
                    'options': options,
                    'correct_answer': row.get('社群答案', row.get('正確答案', 'A')).strip().upper(),
                    'explanation': f"正確答案：{row.get('社群答案', 'A')}"
                }
                
                # 預設都放到 SAA
                questions['SAA'].append(question_data)
                saa_count += 1
        
        print(f"✅ 成功載入 {len(questions['SAA'])} 題 SAA 題目")
        
    except Exception as e:
        print(f"❌ 載入 CSV 失敗：{e}")
        # 使用範例題目
        questions['SAA'] = [
            {
                'id': 0,
                'question': '某公司需要在AWS上部署一個需要處理突發流量的網站，但預算有限。以下哪種EC2購買選項最適合？',
                'options': {
                    'A': 'On-Demand Instances',
                    'B': 'Reserved Instances',
                    'C': 'Spot Instances',
                    'D': 'Savings Plans'
                },
                'correct_answer': 'C',
                'explanation': 'Spot Instances 可以以更低的價格使用未使用的 EC2 容量。'
            }
        ]
    
    return questions

# 載入題庫
QUESTIONS = load_questions_from_csv()

# 儲存用戶狀態
user_data = {}

@app.route("/")
def home():
    return "AWS LINE Bot is running! ✅"

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
    text = event.message.text.strip()
    
    # 開始測驗
    if any(keyword in text.lower() for keyword in ['開始', 'start', '測驗', '考試', '重新']):
        user_data[user_id] = {
            'exam_type': None,
            'current_question': 0,
            'score': 0,
            'total_questions': 0,
            'asked_questions': []
        }
        
        buttons_template = ButtonsTemplate(
            title='🎓 AWS 認證考試',
            text='選擇考試類型：',
            actions=[
                PostbackAction(
                    label='📘 Solutions Architect (SAA)',
                    data='exam_type=SAA'
                ),
                PostbackAction(
                    label='📗 Professional (SAP)',
                    data='exam_type=SAP'
                )
            ]
        )
        
        template_message = TemplateSendMessage(
            alt_text='選擇考試類型',
            template=buttons_template
        )
        
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text='👋 歡迎！請選擇考試類型'),
                template_message
            ]
        )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='💡 請輸入「開始」來開始測驗！')
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    
    params = dict(item.split('=') for item in data.split('&'))
    
    # 選擇考試類型
    if 'exam_type' in params:
        exam_type = params['exam_type']
        
        if len(QUESTIONS.get(exam_type, [])) == 0:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f'❌ {exam_type} 題庫目前沒有題目，請選擇 SAA。')
            )
            return
        
        user_data[user_id] = {
            'exam_type': exam_type,
            'current_question': 0,
            'score': 0,
            'total_questions': min(10, len(QUESTIONS[exam_type])),
            'asked_questions': []
        }
        
        send_question(event.reply_token, user_id)
    
    # 回答問題
    elif 'answer' in params:
        question_id = int(params['question_id'])
        answer = params['answer'].upper()
        exam_type = user_data[user_id]['exam_type']
        
        question = None
        for q in QUESTIONS[exam_type]:
            if q['id'] == question_id:
                question = q
                break
        
        if not question:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='❌ 錯誤，請重新開始')
            )
            return
        
        correct = question['correct_answer'].upper()
        is_correct = (answer == correct)
        
        if is_correct:
            user_data[user_id]['score'] += 1
            result = "✅ 答對了！\n\n"
        else:
            result = f"❌ 答錯了！\n正確答案：{correct}\n\n"
        
        result += f"💡 {question['explanation']}\n\n"
        result += f"📊 目前：{user_data[user_id]['score']}/{user_data[user_id]['current_question'] + 1}"
        
        user_data[user_id]['current_question'] += 1
        
        if user_data[user_id]['current_question'] < user_data[user_id]['total_questions']:
            buttons_template = ButtonsTemplate(
                title='繼續測驗',
                text='準備好了嗎？',
                actions=[
                    PostbackAction(
                        label='➡️ 下一題',
                        data='next_question=true'
                    )
                ]
            )
            
            messages = [
                TextSendMessage(text=result),
                TemplateSendMessage(
                    alt_text='下一題',
                    template=buttons_template
                )
            ]
        else:
            final_score = user_data[user_id]['score']
            total = user_data[user_id]['total_questions']
            percentage = (final_score / total) * 100
            
            final_msg = f"🎉 測驗完成！\n\n"
            final_msg += f"得分：{final_score}/{total}\n"
            final_msg += f"正確率：{percentage:.0f}%\n\n"
            
            if percentage >= 80:
                final_msg += "🏆 優秀！"
            elif percentage >= 60:
                final_msg += "💪 不錯！"
            else:
                final_msg += "📚 繼續加油！"
            
            messages = [
                TextSendMessage(text=result),
                TextSendMessage(text=final_msg),
                TextSendMessage(text='輸入「開始」重新測驗')
            ]
        
        line_bot_api.reply_message(event.reply_token, messages)
    
    elif 'next_question' in params:
        send_question(event.reply_token, user_id)

def send_question(reply_token, user_id):
    exam_type = user_data[user_id]['exam_type']
    asked = user_data[user_id]['asked_questions']
    
    available = [q for q in QUESTIONS[exam_type] if q['id'] not in asked]
    
    if not available:
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text='沒有更多題目了！')
        )
        return
    
    question = random.choice(available)
    user_data[user_id]['asked_questions'].append(question['id'])
    
    current = user_data[user_id]['current_question'] + 1
    total = user_data[user_id]['total_questions']
    
    # 建立選項按鈕
    actions = []
    for key in ['A', 'B', 'C', 'D']:
        if key in question['options']:
            option = question['options'][key]
            label = f"{key}. {option[:12]}..." if len(option) > 12 else f"{key}. {option}"
            
            actions.append(
                PostbackAction(
                    label=label,
                    data=f"question_id={question['id']}&answer={key}"
                )
            )
    
    # 顯示完整題目
    full_question = f"【第 {current}/{total} 題】\n\n{question['question']}\n\n"
    for key in ['A', 'B', 'C', 'D']:
        if key in question['options']:
            full_question += f"{key}. {question['options'][key]}\n"
    
    buttons_template = ButtonsTemplate(
        title=f'第 {current}/{total} 題',
        text='請選擇答案',
        actions=actions[:4]
    )
    
    messages = [
        TextSendMessage(text=full_question),
        TemplateSendMessage(
            alt_text='選擇答案',
            template=buttons_template
        )
    ]
    
    line_bot_api.reply_message(reply_token, messages)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
