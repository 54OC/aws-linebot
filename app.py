from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    PostbackEvent, TemplateSendMessage, ButtonsTemplate,
    PostbackAction
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
            for row in reader:
                exam_type = row.get('考試類型', 'SAA').upper()
                
                question_data = {
                    'id': len(questions[exam_type]),
                    'question': row.get('題目', row.get('中文翻譯', '')),
                    'options': {
                        'A': row.get('選項A', row.get('A', '')),
                        'B': row.get('選項B', row.get('B', '')),
                        'C': row.get('選項C', row.get('C', '')),
                        'D': row.get('選項D', row.get('D', ''))
                    },
                    'correct_answer': row.get('正確答案', row.get('社群答案', 'A')),
                    'explanation': row.get('解析', row.get('詳解', '無解析'))
                }
                
                if exam_type in questions:
                    questions[exam_type].append(question_data)
    
    except FileNotFoundError:
        print("⚠️ CSV 檔案不存在，使用預設題庫")
        # 預設題庫（如果 CSV 不存在）
        questions = {
            'SAA': [
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
                    'explanation': 'Spot Instances 可以以更低的價格使用未使用的 EC2 容量，非常適合處理突發流量且預算有限的場景。'
                }
            ],
            'SAP': []
        }
    
    return questions

# 載入題庫
QUESTIONS = load_questions_from_csv()

# 儲存用戶狀態
user_data = {}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    
    return 'OK'

@app.route("/")
def home():
    return "AWS LINE Bot is running!"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.lower()
    
    # 開始或重新開始
    if text in ['開始', '重新開始', 'start', '測驗', '考試']:
        user_data[user_id] = {
            'exam_type': None,
            'current_question': 0,
            'score': 0,
            'total_questions': 0,
            'asked_questions': []
        }
        
        # 顯示考試類型選擇
        buttons_template = ButtonsTemplate(
            title='🎓 AWS 認證考試練習',
            text='請選擇您要練習的考試類型：',
            actions=[
                PostbackAction(
                    label='📘 SAA (Solutions Architect)',
                    data='exam_type=SAA'
                ),
                PostbackAction(
                    label='📗 SAP (Professional)',
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
                TextSendMessage(text='👋 歡迎使用 AWS 認證考試練習機器人！'),
                template_message
            ]
        )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='💡 請輸入「開始」來開始測驗！\n或輸入「重新開始」重新測驗。')
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    
    # 解析 postback data
    params = dict(item.split('=') for item in data.split('&'))
    
    # 選擇考試類型
    if 'exam_type' in params:
        exam_type = params['exam_type']
        
        if len(QUESTIONS[exam_type]) == 0:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f'❌ 抱歉，{exam_type} 題庫目前沒有題目。\n請選擇其他考試類型或聯絡管理員。')
            )
            return
        
        user_data[user_id]['exam_type'] = exam_type
        user_data[user_id]['current_question'] = 0
        user_data[user_id]['score'] = 0
        user_data[user_id]['total_questions'] = min(10, len(QUESTIONS[exam_type]))  # 每次最多10題
        user_data[user_id]['asked_questions'] = []
        
        # 發送第一題
        send_question(event.reply_token, user_id)
    
    # 回答問題
    elif 'answer' in params:
        question_id = int(params['question_id'])
        answer = params['answer']
        exam_type = user_data[user_id]['exam_type']
        
        # 找到對應題目
        question = None
        for q in QUESTIONS[exam_type]:
            if q['id'] == question_id:
                question = q
                break
        
        if not question:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='❌ 題目載入錯誤，請重新開始。')
            )
            return
        
        correct = question['correct_answer'].upper()
        is_correct = (answer.upper() == correct)
        
        if is_correct:
            user_data[user_id]['score'] += 1
            result = f"✅ 答對了！\n\n"
        else:
            result = f"❌ 答錯了！\n正確答案是：{correct}\n\n"
        
        result += f"📝 詳解：\n{question['explanation']}\n\n"
        result += f"📊 目前得分：{user_data[user_id]['score']}/{user_data[user_id]['current_question'] + 1}"
        
        # 移到下一題
        user_data[user_id]['current_question'] += 1
        
        # 檢查是否還有題目
        if user_data[user_id]['current_question'] < user_data[user_id]['total_questions']:
            # 繼續下一題的按鈕
            buttons_template = ButtonsTemplate(
                title='📋 答題結果',
                text='點擊下方按鈕繼續',
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
                    alt_text='繼續答題',
                    template=buttons_template
                )
            ]
        else:
            # 測驗結束
            final_score = user_data[user_id]['score']
            total = user_data[user_id]['total_questions']
            percentage = (final_score / total) * 100
            
            final_msg = f"🎉 測驗完成！\n\n"
            final_msg += f"📊 最終成績\n"
            final_msg += f"正確：{final_score} 題\n"
            final_msg += f"總題數：{total} 題\n"
            final_msg += f"分數：{percentage:.1f}%\n\n"
            
            if percentage >= 80:
                final_msg += "🏆 太棒了！表現優異！"
            elif percentage >= 60:
                final_msg += "💪 不錯！再加強一下就更好了！"
            else:
                final_msg += "📚 建議多複習相關知識點喔！"
            
            messages = [
                TextSendMessage(text=result),
                TextSendMessage(text=final_msg),
                TextSendMessage(text='輸入「重新開始」可以再次測驗！')
            ]
        
        line_bot_api.reply_message(event.reply_token, messages)
    
    # 繼續下一題
    elif 'next_question' in params:
        send_question(event.reply_token, user_id)

def send_question(reply_token, user_id):
    exam_type = user_data[user_id]['exam_type']
    asked_questions = user_data[user_id]['asked_questions']
    
    # 隨機選擇一個未問過的題目
    available_questions = [q for q in QUESTIONS[exam_type] if q['id'] not in asked_questions]
    
    if not available_questions:
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text='❌ 沒有更多題目了！')
        )
        return
    
    question = random.choice(available_questions)
    user_data[user_id]['asked_questions'].append(question['id'])
    
    current_num = user_data[user_id]['current_question'] + 1
    total_num = user_data[user_id]['total_questions']
    
    # 建立選項按鈕
    actions = []
    for key in ['A', 'B', 'C', 'D']:
        if question['options'].get(key):
            option_text = question['options'][key]
            # LINE 按鈕文字限制 20 字
            display_text = f"{key}. {option_text[:15]}..." if len(option_text) > 15 else f"{key}. {option_text}"
            
            actions.append(
                PostbackAction(
                    label=display_text,
                    data=f"question_id={question['id']}&answer={key}"
                )
            )
    
    # 題目文字（如果太長要分段）
    question_text = f"【第 {current_num}/{total_num} 題】\n\n{question['question']}"
    
    # 選項文字
    options_text = "\n\n"
    for key in ['A', 'B', 'C', 'D']:
        if question['options'].get(key):
            options_text += f"{key}. {question['options'][key]}\n"
    
    buttons_template = ButtonsTemplate(
        title=f'第 {current_num}/{total_num} 題',
        text='請選擇答案：',
        actions=actions[:4]  # LINE 最多 4 個按鈕
    )
    
    template_message = TemplateSendMessage(
        alt_text=f"第 {current_num} 題",
        template=buttons_template
    )
    
    messages = [
        TextSendMessage(text=question_text + options_text),
        template_message
    ]
    
    line_bot_api.reply_message(reply_token, messages)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
