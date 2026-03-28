from flask import Flask, request
import requests
import os
import random
import re
import openpyxl
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

def load_all_questions():
    filename = 'AWS_SAA_SAP_繁體中文版.xlsx'
    if not os.path.exists(filename): return f"找不到檔案: {filename}"
    
    try:
        wb = openpyxl.load_workbook(filename, data_only=True)
        for cat in ['SAA', 'SAP']:
            if cat not in wb.sheetnames: continue
            sheet = wb[cat]
            # 取得標題列並去除空白
            headers = [str(cell.value).strip() if cell.value else "" for cell in sheet[1]]
            
            # 自動搜尋欄位索引 (容錯邏輯)
            def find_col(keywords):
                for i, h in enumerate(headers):
                    if any(k in h for k in keywords): return i
                return None

            col = {
                'q_cn': find_col(['題目(中)', '題目（中）']),
                'q_en': find_col(['題目(英)', '題目（英）']),
                'opt_cn': find_col(['選項(中)', '選項（中）']),
                'opt_en': find_col(['選項(英)', '選項（英）']),
                'ans': find_col(['正確答案']),
                'exp_cn': find_col(['解析(中)', '解析（中）']),
                'exp_en': find_col(['答案備註', '解析(英)'])
            }

            for row in sheet.iter_rows(min_row=2, values_only=True):
                # 只要中英文題目有一個存在就載入
                q_text = row[col['q_cn']] if col['q_cn'] is not None else row[col['q_en']]
                if q_text:
                    q_data = {
                        'q_cn': str(row[col['q_cn']] or "").strip() if col['q_cn'] is not None else "",
                        'q_en': str(row[col['q_en']] or "").strip() if col['q_en'] is not None else "",
                        'opt_cn_raw': str(row[col['opt_cn']] or "").strip() if col['opt_cn'] is not None else "",
                        'opt_en_raw': str(row[col['opt_en']] or "").strip() if col['opt_en'] is not None else "",
                        'ans': str(row[col['ans']] or "A").strip().upper(),
                        'exp_cn': str(row[col['exp_cn']] or "暫無中文解析。").strip() if col['exp_cn'] is not None else "暫無中文解析。",
                        'exp_en': str(row[col['exp_en']] or "No English explanation.").strip() if col['exp_en'] is not None else "No English explanation."
                    }
                    q_data['opts_cn'] = parse_options(q_data['opt_cn_raw'])
                    q_data['opts_en'] = parse_options(q_data['opt_en_raw'])
                    QUESTIONS[cat].append(q_data)
        
        total = len(QUESTIONS['SAA']) + len(QUESTIONS['SAP'])
        return "成功" if total > 0 else "Excel 內沒有抓到任何題目"
    except Exception as e:
        return f"讀取錯誤: {str(e)}"

def parse_options(raw):
    opts = {}
    if not raw: return {}
    for char in ['A', 'B', 'C', 'D']:
        pattern = rf"{char}[.)](.*?)(?=[A-D][.)]|$)"
        match = re.search(pattern, raw, re.DOTALL)
        opts[char] = match.group(1).strip() if match else ""
    return opts

load_status = load_all_questions()

def send_line(reply_token, messages):
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'}
    payload = {'replyToken': reply_token, 'messages': messages}
    requests.post(LINE_REPLY_URL, headers=headers, json=payload)

# --- Flex UI ---

def welcome_flex():
    return {
        "type": "flex", "altText": "AWS 學習助手",
        "contents": {
            "type": "bubble",
            "header": { "type": "box", "layout": "vertical", "contents": [{ "type": "text", "text": "AWS CERTIFIED GUIDE", "weight": "bold", "color": COLOR_TITLE, "size": "sm" }] },
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": "今天要挑戰哪一科？", "weight": "bold", "size": "lg", "color": COLOR_TEXT },
                { "type": "text", "text": "💡 傳送任何訊息皆可回到此選單", "size": "xs", "color": "#BBBBBB", "margin": "md" }
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
                { "type": "text", "text": f"📍 {exam_type} 考題", "weight": "bold", "color": COLOR_TEXT },
                { "type": "text", "text": "請選擇練習語言：", "size": "sm", "margin": "sm" }
            ]},
            "footer": { "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "action": { "type": "postback", "label": "中文答題 (Traditional Chinese)", "data": f"action=start&lang=cn&type={exam_type}" } },
                { "type": "button", "style": "primary", "color": COLOR_SECONDARY, "action": { "type": "postback", "label": "英文答題 (English)", "data": f"action=start&lang=en&type={exam_type}" } }
            ]}
        }
    }

def question_flex(cat, lang, idx):
    q = QUESTIONS[cat][idx]
    title = q['q_cn'] if lang == 'cn' and q['q_cn'] else q['q_en']
    opts = q['opts_cn'] if lang == 'cn' and q['opts_cn'] else q['opts_en']
    
    opt_list = []
    for char in ['A', 'B', 'C', 'D']:
        if opts.get(char):
            opt_list.append({ "type": "text", "text": f"{char}. {opts[char]}", "wrap": True, "size": "sm", "margin": "md", "color": "#666666" })

    return {
        "type": "flex", "altText": "新題目",
        "contents": {
            "type": "bubble",
            "body": { "type": "box", "layout": "vertical", "contents": [
                { "type": "text", "text": f"AWS {cat} ({lang.upper()})", "size": "xs", "color": COLOR_PRIMARY, "weight": "bold" },
                { "type": "text", "text": title, "wrap": True, "weight": "bold", "margin": "md", "color": COLOR_TEXT },
                { "type": "separator", "margin": "xl" },
                { "type": "box", "layout": "vertical", "margin": "md", "contents": opt_list }
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
        
        # 🟢 修正重點：傳送任何訊息（文字、貼圖等）都跑出主選單
        if event['type'] == 'message' or event['type'] == 'follow':
            if load_status != "成功":
                send_line(tk, [{"type": "text", "text": f"❌ 系統錯誤：{load_status}\n請檢查 Excel 欄位名稱或檔名。"}])
            else:
                send_line(tk, [welcome_flex()])
            
        elif event['type'] == 'postback':
            data = parse_qs(event['postback']['data'])
            
            if data.get('menu', [None])[0] == 'lang':
                send_line(tk, [lang_select_flex(data['type'][0])])
            
            elif data.get('action', [None])[0] == 'start':
                lang, cat = data['lang'][0], data['type'][0]
                pool = [i for i, q in enumerate(QUESTIONS[cat]) if (q['q_cn'] if lang=='cn' else q['q_en'])]
                if not pool:
                    send_line(tk, [{"type": "text", "text": f"目前 {cat} {lang.upper()} 題庫尚無內容。"}])
                else:
                    send_line(tk, [question_flex(cat, lang, random.choice(pool))])
            
            elif 'ans' in data:
                u_ans, c_ans, q_idx, lang, cat = data['ans'][0], data['c'][0], int(data['id'][0]), data['l'][0], data['t'][0]
                explain = QUESTIONS[cat][q_idx]['exp_cn'] if lang == 'cn' else QUESTIONS[cat][q_idx]['exp_en']
                res = "🎉 答對了！" if u_ans == c_ans else f"❌ 答錯了，正解是 {c_ans}"
                
                send_line(tk, [
                    { "type": "text", "text": f"{res}\n\n💡 解析：\n{explain}" },
                    { "type": "flex", "altText": "下一步", "contents": {
                        "type": "bubble", "size": "small", "body": { "type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                            { "type": "button", "style": "primary", "color": COLOR_PRIMARY, "action": { "type": "postback", "label": "挑戰下一題", "data": f"action=start&lang={lang}&type={cat}" } },
                            { "type": "button", "style": "secondary", "action": { "type": "postback", "label": "回主選單", "data": "menu=main" } }
                        ]}}
                    }
                ])
            elif data.get('menu', [None])[0] == 'main':
                send_line(tk, [welcome_flex()])
    return 'OK'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
