from flask import Flask, request
import requests
import os
import random
import re
import csv
from urllib.parse import parse_qs

app = Flask(__name__)

# LINE 設定
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
LINE_REPLY_URL = 'https://api.line.me/v2/bot/message/reply'

# 🎨 莫蘭迪配色
COLOR_PRIMARY = "#95A3A4"   # 灰綠
COLOR_SECONDARY = "#B8A99A" # 砂褐
COLOR_TITLE = "#7E8989"     # 煙燻灰
COLOR_TEXT = "#555555"      # 深灰

# 全域題庫
QUESTIONS = {'SAA': [], 'SAP': []}

def parse_options(raw_text):
    """解析 A. B. C. D. 格式的選項"""
    opts = {}
    if not raw_text: return opts
    # 支援 A. B. C. D. 或 A) B) C) D) 格式
    for char in ['A', 'B', 'C', 'D']:
        pattern = rf"{char}[.)](.*?)(?=[A-D][.)]|$)"
        match = re.search(pattern, str(raw_text), re.DOTALL)
        opts[char] = match.group(1).strip() if match else ""
    return opts

def load_from_csv():
    # 根據妳提供的檔案名稱設定
    files = {
        'SAA': 'AWS_SAA_繁體中文版.csv',
        'SAP': 'AWS_SAP_繁體中文版.csv'
    }
    
    for cat, filename in files.items():
        if not os.path.exists(filename):
            print(f"⚠️ 找不到檔案: {filename}")
            continue
        
        try:
            with open(filename, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 只要題目(英)或(中)其中一個有值就抓
                    if row.get('題目(英)') or row.get('題目(中)'):
                        q_data = {
                            'q_cn': row.get('題目(中)', '').strip(),
                            'q_en': row.get('題目(英)', '').strip(),
                            'ans': row.get('正確答案', 'A').strip().upper(),
                            'exp_cn': row.get('解析(中)', '').strip() or row.get('答案備註', '').strip() or "暫無解析。",
                            'exp_en': row.get('答案備註', '').strip() or "No explanation available.",
                            'opts_cn': parse_options(row.get('選項(中)', '')),
                            'opts_en': parse_options(row.get('選項(英)', ''))
                        }
                        QUESTIONS[cat].append(q_data)
            print(f"✅ {cat} 載入成功，共 {len(QUESTIONS[cat])} 題")
        except Exception as e:
            print(f"❌ {cat} 載入失敗: {e}")

load_from_csv()

def send_line(reply_token, messages):
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'}
    payload = {'replyToken': reply_token, 'messages': messages}
    requests.post(LINE_REPLY_URL, headers=headers, json=payload)

# --- Flex UI 設計 ---

def welcome_flex():
    return {
        "type": "flex", "altText": "AWS 題庫主選單",
        "contents": {
            "type": "bubble",
            "header": { "type": "box", "layout": "vertical", "contents": [{ "type": "text", "text": "AWS CERTIFIED EXAM", "weight": "bold", "color": COLOR_TITLE, "size": "sm" }] },
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": "請選擇練習科目：", "weight": "bold", "size": "lg", "color": COLOR_TEXT },
                { "type": "text", "text": "隨意傳送訊息可隨時回到此選單", "size": "xs", "color": "#BBBBBB", "margin": "md" }
            ]},
            "footer": { "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "action": { "type": "postback", "label": "SAA (助理架構師)", "data": "menu=lang&type=SAA" } },
                { "type": "button", "style": "primary", "color": COLOR_SECONDARY, "action": { "type": "postback", "label": "SAP (專業架構師)", "data": "menu=lang&type=SAP" } }
            ]}
        }
    }

def lang_select_flex(exam_type):
    return {
        "type": "flex", "altText": "選擇語言",
        "contents": {
            "type": "bubble",
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": f"📍 目前科目：{exam_type}", "weight": "bold", "color": COLOR_TEXT },
                { "type": "text", "text": "請選擇顯示語言：", "size": "sm", "margin": "sm" }
            ]},
            "footer": { "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "action": { "type": "postback", "label": "中文版 (Traditional Chinese)", "data": f"action=start&lang=cn&type={exam_type}" } },
                { "type": "button", "style": "primary", "color": COLOR_SECONDARY, "action": { "type": "postback", "label": "英文版 (English)", "data": f"action=start&lang=en&type={exam_type}" } }
            ]}
        }
    }

def question_flex(cat, lang, idx):
    q = QUESTIONS[cat][idx]
    title = q['q_cn'] if lang == 'cn' and q['q_cn'] else q['q_en']
    opts = q['opts_cn'] if lang == 'cn' and q['opts_cn'] else q['opts_en']
    
    # 選項內容清單（解決遮擋關鍵：在此處使用 text 並開啟 wrap）
    opt_contents = []
    for char in ['A', 'B', 'C', 'D']:
        if opts.get(char):
            opt_contents.append({ "type": "text", "text": f"{char}. {opts[char]}", "wrap": True, "size": "sm", "margin": "md", "color": "#666666" })

    return {
        "type": "flex", "altText": "考試練習中",
        "contents": {
            "type": "bubble",
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": f"AWS {cat} - {lang.upper()}", "size": "xs", "color": COLOR_PRIMARY, "weight": "bold" },
                { "type": "text", "text": title, "wrap": True, "weight": "bold", "margin": "md", "color": COLOR_TEXT, "size": "md" },
                { "type": "separator", "margin": "xl" },
                { "type": "box", "layout": "vertical", "margin": "md", "contents": opt_contents }
            ]},
            "footer": { "type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "height": "sm", "action": { "type": "postback", "label": "A", "data": f"ans=A&c={q['ans']}&id={idx}&l={lang}&t={cat}" } },
                { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "height": "sm", "action": { "type": "postback", "label": "B", "data": f"ans=B&c={q['ans']}&id={idx}&l={lang}&t={cat}" } },
                { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "height": "sm", "action": { "type": "postback", "label": "C", "data": f"ans=C&c={q['ans']}&id={idx}&l={lang}&t={cat}" } },
                { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "height": "sm", "action": { "type": "postback", "label": "D", "data": f"ans=D&c={q['ans']}&id={idx}&l={lang}&t={cat}" } }
            ]}
        }
    }

@app.route("/callback", methods=['POST'])
def callback():
    events = request.json.get('events', [])
    for event in events:
        tk = event['replyToken']
        
        # 🟢 隨意傳送訊息就回主選單
        if event['type'] == 'message' or event['type'] == 'follow':
            send_line(tk, [welcome_flex()])
            
        elif event['type'] == 'postback':
            data = parse_qs(event['postback']['data'])
            
            # 選擇語言分頁
            if data.get('menu', [None])[0] == 'lang':
                send_line(tk, [lang_select_flex(data['type'][0])])
            
            # 開始出題邏輯
            elif data.get('action', [None])[0] == 'start':
                lang, cat = data['lang'][0], data['type'][0]
                pool = [i for i, q in enumerate(QUESTIONS[cat]) if (q['q_cn'] if lang=='cn' else q['q_en'])]
                if not pool:
                    send_line(tk, [{"type": "text", "text": "該科目目前沒有對應語言的題目。"}])
                else:
                    send_line(tk, [question_flex(cat, lang, random.choice(pool))])
            
            # 答題判斷邏輯
            elif 'ans' in data:
                u_ans, c_ans, q_idx, lang, cat = data['ans'][0], data['c'][0], int(data['id'][0]), data['l'][0], data['t'][0]
                explain = QUESTIONS[cat][q_idx]['exp_cn'] if lang == 'cn' else QUESTIONS[cat][q_idx]['exp_en']
                res = "🎉 答對了！" if u_ans == c_ans else f"❌ 答錯了，正解是 {c_ans}"
                
                send_line(tk, [
                    { "type": "text", "text": f"{res}\n\n💡 解析：\n{explain}" },
                    { "type": "flex", "altText": "下一步", "contents": {
                        "type": "bubble", "size": "small", "body": { "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                            { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "action": { "type": "postback", "label": "下一題", "data": f"action=start&lang={lang}&type={cat}" } },
                            { "type": "button", "style": "secondary", "action": { "type": "postback", "label": "回選單", "data": "menu=main" } }
                        ]}}
                    }
                ])
            elif data.get('menu', [None])[0] == 'main':
                send_line(tk, [welcome_flex()])
    return 'OK'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
