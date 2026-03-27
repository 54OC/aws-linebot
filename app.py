from flask import Flask, request
import requests
import os
import csv
import random
import hashlib
import hmac
import base64
import re
from urllib.parse import parse_qs

app = Flask(__name__)

# LINE 設定
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
LINE_REPLY_URL = 'https://api.line.me/v2/bot/message/reply'

# 1. 強化版題庫讀取 (支援雙語)
def load_questions():
    questions = []
    if not os.path.exists('aws_questions.csv'): return []
    try:
        with open('aws_questions.csv', 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 準備資料結構
                q_data = {
                    'q_cn': row.get('題目(中)', '').strip(),
                    'q_en': row.get('題目(英)', '').strip(),
                    'opt_cn_raw': row.get('選項(中)', '').strip(),
                    'opt_en_raw': row.get('選項(英)', '').strip(),
                    'ans': row.get('正確答案', 'A').strip().upper(),
                    'exp': row.get('解析(中)', '').strip() or "加油！祝妳考試順利。"
                }
                
                # 自動拆解雙語選項 A. B. C. D.
                q_data['opts_cn'] = parse_options(q_data['opt_cn_raw'])
                q_data['opts_en'] = parse_options(q_data['opt_en_raw'])

                if q_data['q_cn'] or q_data['q_en']:
                    questions.append(q_data)
        return questions
    except Exception as e:
        print(f"讀取錯誤: {e}")
        return []

def parse_options(opt_raw):
    opts = {}
    for char in ['A', 'B', 'C', 'D']:
        pattern = rf"{char}[.)](.*?)(?=[B-D][.)]|$)"
        match = re.search(pattern, opt_raw, re.DOTALL)
        opts[char] = match.group(1).strip() if match else f"Option {char}"
    return opts

QUESTIONS = load_questions()

# 2. LINE 工具
def send_line(reply_token, messages):
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'}
    payload = {'replyToken': reply_token, 'messages': messages}
    requests.post(LINE_REPLY_URL, headers=headers, json=payload)

# 3. 各種 Flex Message 模板
def welcome_flex():
    return {
        "type": "flex", "altText": "AWS 助手",
        "contents": {
            "type": "bubble",
            "header": { "type": "box", "layout": "vertical", "contents": [{ "type": "text", "text": "AWS 證照練習助手", "weight": "bold", "color": "#E67E22", "size": "xl" }] },
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": "妳好！準備好要挑戰了嗎？", "weight": "bold" },
                { "type": "text", "text": "💡 貼心提醒：由於本機器人部署於免費雲端空間，若一段時間未運行，首次點擊可能會有 15-30 秒的「熱機延遲」。若按鈕沒反應，請稍等片刻或再點擊一次，感謝您的耐心！", "size": "xs", "color": "#aaaaaa", "margin": "md", "wrap": True }
            ]},
            "footer": { "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                { "type": "button", "style": "primary", "color": "#E67E22", "action": { "type": "postback", "label": "SAA (助理架構師)", "data": "menu=lang&type=saa" } },
                { "type": "button", "style": "secondary", "action": { "type": "postback", "label": "SAP (專業架構師)", "data": "menu=lang&type=sap" } }
            ]}
        }
    }

def lang_select_flex(exam_type):
    return {
        "type": "flex", "altText": "請選擇語言",
        "contents": {
            "type": "bubble",
            "body": { "type": "box", "layout": "vertical", "contents": [{ "type": "text", "text": f"妳選擇了 {exam_type.upper()}，請選擇出題語言：", "weight": "bold" }] },
            "footer": { "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                { "type": "button", "style": "primary", "action": { "type": "postback", "label": "中文答題 (Traditional Chinese)", "data": f"action=start&lang=cn&type={exam_type}" } },
                { "type": "button", "style": "primary", "action": { "type": "postback", "label": "英文答題 (English)", "data": f"action=start&lang=en&type={exam_type}" } }
            ]}
        }
    }

def question_flex(idx, lang):
    q = QUESTIONS[idx]
    title = q['q_cn'] if lang == 'cn' else q['q_en']
    opts = q['opts_cn'] if lang == 'cn' else q['opts_en']
    return {
        "type": "flex", "altText": "題目來了",
        "contents": {
            "type": "bubble",
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": f"AWS 隨機練習 (語言: {lang.upper()})", "size": "xs", "color": "#aaaaaa" },
                { "type": "text", "text": title, "wrap": True, "weight": "bold", "margin": "md" },
                { "type": "separator", "margin": "xl" },
                { "type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
                    { "type": "button", "action": { "type": "postback", "label": f"A. {opts['A'][:30]}", "data": f"action=ans&user=A&correct={q['ans']}&idx={idx}&lang={lang}" } },
                    { "type": "button", "action": { "type": "postback", "label": f"B. {opts['B'][:30]}", "data": f"action=ans&user=B&correct={q['ans']}&idx={idx}&lang={lang}" } },
                    { "type": "button", "action": { "type": "postback", "label": f"C. {opts['C'][:30]}", "data": f"action=ans&user=C&correct={q['ans']}&idx={idx}&lang={lang}" } },
                    { "type": "button", "action": { "type": "postback", "label": f"D. {opts['D'][:30]}", "data": f"action=ans&user=D&correct={q['ans']}&idx={idx}&lang={lang}" } }
                ]}
            ]}
        }
    }

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_data(as_text=True)
    events = request.json.get('events', [])
    for event in events:
        if event['type'] == 'follow' or (event['type'] == 'message' and event['message']['type'] == 'text'):
            send_line(event['replyToken'], [welcome_flex()])
            
        elif event['type'] == 'postback':
            # 這裡修正了解析邏輯，改用標準的 URL 參數解析
            data = parse_qs(event['postback']['data'])
            action = data.get('action', [None])[0]
            menu = data.get('menu', [None])[0]
            lang = data.get('lang', ['cn'])[0]
            
            if menu == 'lang':
                exam_type = data.get('type', ['saa'])[0]
                send_line(event['replyToken'], [lang_select_flex(exam_type)])
            
            elif action == 'start':
                idx = random.randint(0, len(QUESTIONS)-1)
                send_line(event['replyToken'], [question_flex(idx, lang)])
            
            elif action == 'ans':
                user_ans = data.get('user', [''])[0]
                correct_ans = data.get('correct', [''])[0]
                q_idx = int(data.get('idx', [0])[0])
                
                is_correct = (user_ans == correct_ans)
                res_text = "🎉 答對了！" if is_correct else f"❌ 答錯了，正解是 {correct_ans}"
                
                result_msg = [
                    { "type": "text", "text": f"{res_text}\n\n💡 解析：\n{QUESTIONS[q_idx]['exp']}" },
                    { "type": "flex", "altText": "下一步", "contents": {
                        "type": "bubble", "body": { "type": "box", "layout": "vertical", "spacing": "md", "contents": [
                            { "type": "button", "style": "primary", "action": { "type": "postback", "label": "挑戰下一題", "data": f"action=start&lang={lang}" } },
                            { "type": "button", "style": "secondary", "action": { "type": "postback", "label": "回主選單/更換語言", "data": "menu=main" } }
                        ]}}
                    }
                ]
                send_line(event['replyToken'], result_msg)
            
            elif data.get('menu', [None])[0] == 'main':
                send_line(event['replyToken'], [welcome_flex()])

    return 'OK'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
