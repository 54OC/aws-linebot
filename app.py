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

# LINE 設定 (由環境變數讀取)
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
LINE_REPLY_URL = 'https://api.line.me/v2/bot/message/reply'

# 1. 讀取 CSV (防呆與雙語解析強化)
def load_questions():
    questions = []
    if not os.path.exists('aws_questions.csv'): return []
    try:
        # 使用 utf-8-sig 讀取，防止 Excel 產生的亂碼
        with open('aws_questions.csv', 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                q_data = {
                    'q_cn': row.get('題目(中)', '').strip(),
                    'q_en': row.get('題目(英)', '').strip(),
                    'opt_cn_raw': row.get('選項(中)', '').strip(),
                    'opt_en_raw': row.get('選項(英)', '').strip(),
                    'ans': row.get('正確答案', 'A').strip().upper(),
                    # 解析抓取修正
                    'exp_cn': row.get('解析(中)', '').strip() or row.get('答案備註', '').strip() or "暫無中文解析。",
                    'exp_en': row.get('解析(英)', '').strip() or "No explanation available for English version yet."
                }
                
                # 防呆：如果中文題目是空的，顯示英文
                if not q_data['q_cn']: q_data['q_cn'] = q_data['q_en']
                
                # 拆解選項
                q_data['opts_cn'] = parse_options(q_data['opt_cn_raw'])
                q_data['opts_en'] = parse_options(q_data['opt_en_raw'])

                # 只要有題目就收入
                if q_data['q_cn'] or q_data['q_en']:
                    questions.append(q_data)
        print(f"✅ 成功載入 {len(questions)} 題")
        return questions
    except Exception as e:
        print(f"❌ 讀取失敗: {e}")
        return []

def parse_options(opt_raw):
    opts = {}
    for char in ['A', 'B', 'C', 'D']:
        # 正規表達式：抓取 A. 到下一選項或結尾之間的文字
        pattern = rf"{char}[.)](.*?)(?=[A-D][.)]|$)"
        match = re.search(pattern, opt_raw, re.DOTALL)
        opts[char] = match.group(1).strip() if match else f"Option {char}"
    return opts

QUESTIONS = load_questions()

def send_line(reply_token, messages):
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'}
    payload = {'replyToken': reply_token, 'messages': messages}
    requests.post(LINE_REPLY_URL, headers=headers, json=payload)

# 2. 開頭與提醒 (保留妳最喜歡的版本)
def welcome_flex():
    return {
        "type": "flex", "altText": "AWS 助手",
        "contents": {
            "type": "bubble",
            "header": { "type": "box", "layout": "vertical", "contents": [{ "type": "text", "text": "AWS 證照練習助手", "weight": "bold", "color": "#E67E22", "size": "xl" }] },
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": "妳好！準備好要挑戰了嗎？", "weight": "bold", "size": "md" },
                { "type": "text", "text": "💡 貼心提醒：由於本機器人部署於免費雲端平台，若一段時間未運行，系統會休眠。首次點擊可能會有 15-30 秒的「熱機延遲」。若按鈕沒反應，請稍等片刻或再次嘗試，感謝您的耐心！", "wrap": True, "size": "xs", "color": "#888888", "margin": "md" }
            ]},
            "footer": { "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                { "type": "button", "style": "primary", "color": "#E67E22", "action": { "type": "postback", "label": "SAA (助理架構師)", "data": "menu=lang&type=saa" } },
                { "type": "button", "style": "secondary", "action": { "type": "postback", "label": "SAP (專業架構師)", "data": "menu=lang&type=sap" } }
            ]}
        }
    }

def lang_select_flex(exam_type):
    return {
        "type": "flex", "altText": "選擇語言",
        "contents": {
            "type": "bubble",
            "body": { "type": "box", "layout": "vertical", "contents": [{ "type": "text", "text": f"妳選擇了 {exam_type.upper()}，請選擇出題語言：", "weight": "bold" }] },
            "footer": { "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                { "type": "button", "style": "primary", "action": { "type": "postback", "label": "中文答題 (Traditional Chinese)", "data": f"action=start&lang=cn&type={exam_type}" } },
                { "type": "button", "style": "primary", "action": { "type": "postback", "label": "英文答題 (English)", "data": f"action=start&lang=en&type={exam_type}" } }
            ]}
        }
    }

# 🌟 重大優化：新的出題卡片設計，解決選項長文字顯示問題
def question_flex(idx, lang):
    q = QUESTIONS[idx]
    title = q['q_cn'] if lang == 'cn' else q['q_en']
    opts = q['opts_cn'] if lang == 'cn' else q['opts_en']
    
    # 建構選項全文區塊 (Body)
    option_texts = []
    for char in ['A', 'B', 'C', 'D']:
        option_texts.append({
            "type": "text",
            "text": f"{char}. {opts[char]}",
            "wrap": True, # 強制換行
            "size": "sm", # 字體稍微縮小，容納更多內容
            "margin": "md"
        })

    return {
        "type": "flex", "altText": "題目來了",
        "contents": {
            "type": "bubble",
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": f"AWS 隨機練習 ({lang.upper()})", "size": "xs", "color": "#aaaaaa" },
                # 題目全文 (支援換行)
                { "type": "text", "text": title, "wrap": True, "weight": "bold", "margin": "md" },
                { "type": "separator", "margin": "xl" },
                # 選項全文顯示區塊
                { "type": "box", "layout": "vertical", "margin": "lg", "contents": option_texts }
            ]},
            # 卡片底部 (Footer) 顯示精簡的答題按鈕
            "footer": {
                "type": "box", "layout": "vertical", "contents": [
                    { "type": "text", "text": "請選擇對應的答案：", "size": "xs", "color": "#aaaaaa", "align": "center", "margin": "sm" },
                    { "type": "box", "layout": "horizontal", "spacing": "md", "margin": "md", "contents": [
                        { "type": "button", "style": "primary", "height": "sm", "action": { "type": "postback", "label": "A", "data": f"action=ans&user=A&correct={q['ans']}&idx={idx}&lang={lang}" } },
                        { "type": "button", "style": "primary", "height": "sm", "action": { "type": "postback", "label": "B", "data": f"action=ans&user=B&correct={q['ans']}&idx={idx}&lang={lang}" } },
                        { "type": "button", "style": "primary", "height": "sm", "action": { "type": "postback", "label": "C", "data": f"action=ans&user=C&correct={q['ans']}&idx={idx}&lang={lang}" } },
                        { "type": "button", "style": "primary", "height": "sm", "action": { "type": "postback", "label": "D", "data": f"action=ans&user=D&correct={q['ans']}&idx={idx}&lang={lang}" } }
                    ]}
                ]
            }
        }
    }

@app.route("/callback", methods=['POST'])
def callback():
    events = request.json.get('events', [])
    for event in events:
        if event['type'] == 'follow' or (event['type'] == 'message' and event['message']['type'] == 'text'):
            send_line(event['replyToken'], [welcome_flex()])
            
        elif event['type'] == 'postback':
            data = parse_qs(event['postback']['data'])
            action = data.get('action', [None])[0]
            menu = data.get('menu', [None])[0]
            lang = data.get('lang', ['cn'])[0]
            
            if menu == 'lang':
                send_line(event['replyToken'], [lang_select_flex(data.get('type', ['saa'])[0])])
            elif action == 'start':
                idx = random.randint(0, len(QUESTIONS)-1)
                send_line(event['replyToken'], [question_flex(idx, lang)])
            elif action == 'ans':
                user_ans, correct_ans, q_idx = data.get('user',[''])[0], data.get('correct',[''])[0], int(data.get('idx',['0'])[0])
                
                # 抓取對應語言的解析
                explain = QUESTIONS[q_idx]['exp_cn'] if lang == 'cn' else QUESTIONS[q_idx]['exp_en']
                res_text = "🎉 答對了！" if user_ans == correct_ans else f"❌ 答錯了，正解是 {correct_ans}"
                
                result_msg = [
                    { "type": "text", "text": f"{res_text}\n\n💡 解析：\n{explain}" },
                    { "type": "flex", "altText": "下一步", "contents": {
                        "type": "bubble", "body": { "type": "box", "layout": "vertical", "spacing": "md", "contents": [
                            { "type": "button", "style": "primary", "action": { "type": "postback", "label": "挑戰下一題", "data": f"action=start&lang={lang}" } },
                            { "type": "button", "style": "secondary", "action": { "type": "postback", "label": "回主選單", "data": "menu=main" } }
                        ]}}
                    }
                ]
                send_line(event['replyToken'], result_msg)
            elif menu == 'main':
                send_line(event['replyToken'], [welcome_flex()])
    return 'OK'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
