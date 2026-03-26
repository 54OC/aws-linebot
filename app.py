from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    QuickReply, QuickReplyButton, MessageAction,
    PostbackEvent, TemplateSendMessage, ButtonsTemplate,
    PostbackAction
)
import json
import os

app = Flask(__name__)

# LINE Bot 設定 - 等等要改成您的
line_bot_api = LineBotApi(os.environ.get('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('CHANNEL_SECRET'))

# 載入題庫
with open('questions.json', 'r', encoding='utf-8') as f:
    QUESTIONS = json.load(f)

# 儲存用戶狀態（實際應用應該用資料庫）
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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text
    
    # 開始或重新開始
    if text in ['開始', '重新開始', 'start']:
        user_data[user_id] = {
            'exam_type': None,
            'current_question': 0,
            'score': 0,
            'total_questions': 0
        }
        
        # 顯示考試類型選擇
        buttons_template = ButtonsTemplate(
            title='選擇 AWS 認證考試',
            text='請選擇您要練習的考試類型：',
            actions=[
                PostbackAction(
                    label='Solutions Architect Associate (SAA)',
                    data='exam_type=SAA'
                ),
                PostbackAction(
                    label='Solutions Architect Professional (SAP)',
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
            template_message
        )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='請輸入「開始」來開始測驗！')
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
        user_data[user_id]['exam_type'] = exam_type
        user_data[user_id]['current_question'] = 0
        user_data[user_id]['score'] = 0
        user_data[user_id]['total_questions'] = len(QUESTIONS[exam_type])
        
        # 發送第一題
        send_question(event.reply_token, user_id)
    
    # 回答問題
    elif 'answer' in params:
        question_id = int(params['question_id'])
        answer = params['answer']
        exam_type = user_data[user_id]['exam_type']
        
        # 找到對應題目
        question = QUESTIONS[exam_type][question_id]
        correct = question['correct_answer']
        is_correct = (answer == correct)
        
        if is_correct:
            user_data[user_id]['score'] += 1
            result = f"✅ 答對了！\n\n"
        else:
            result = f"❌ 答錯了！正確答案是 {correct}\n\n"
        
        result += f"📝 詳解：\n{question['explanation']}\n\n"
        result += f"目前得分：{user_data[user_id]['score']}/{user_data[user_id]['current_question'] + 1}"
        
        # 移到下一題
        user_data[user_id]['current_question'] += 1
        
        # 檢查是否還有題目
        if user_data[user_id]['current_question'] < user_data[user_id]['total_questions']:
            # 繼續下一題的按鈕
            buttons_template = ButtonsTemplate(
                title='答題結果',
                text=result[:60],  # LINE 限制
                actions=[
                    PostbackAction(
                        label='繼續下一題',
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
            
            result += f"\n\n🎉 測驗完成！\n"
            result += f"最終得分：{final_score}/{total} ({percentage:.1f}%)\n"
            
            if percentage >= 80:
                result += "👏 太棒了！繼續保持！"
            elif percentage >= 60:
                result += "💪 不錯！再加強一下就更好了！"
            else:
                result += "📚 建議多複習相關知識點！"
            
            messages = [
                TextSendMessage(text=result),
                TextSendMessage(text='輸入「重新開始」可以再次測驗！')
            ]
        
        line_bot_api.reply_message(event.reply_token, messages)
    
    # 繼續下一題
    elif 'next_question' in params:
        send_question(event.reply_token, user_id)

def send_question(reply_token, user_id):
    exam_type = user_data[user_id]['exam_type']
    question_index = user_data[user_id]['current_question']
    question = QUESTIONS[exam_type][question_index]
    
    # 建立選項按鈕
    actions = []
    for key, value in question['options'].items():
        actions.append(
            PostbackAction(
                label=f"{key}. {value[:10]}...",  # LINE 按鈕文字限制
                data=f"question_id={question_index}&answer={key}"
            )
        )
    
    buttons_template = ButtonsTemplate(
        title=f"第 {question_index + 1} 題",
        text=question['question'][:60],  # LINE 文字限制
        actions=actions
    )
    
    template_message = TemplateSendMessage(
        alt_text=f"第 {question_index + 1} 題",
        template=buttons_template
    )
    
    messages = [
        TextSendMessage(text=f"【第 {question_index + 1} 題】\n\n{question['question']}"),
        template_message
    ]
    
    line_bot_api.reply_message(reply_token, messages)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)