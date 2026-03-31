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

# 🎨 莫蘭迪配色（更柔和的版本）
COLORS = {
    'primary': '#9CAF88',      # 柔和橄欖綠
    'secondary': '#C9B8A8',    # 溫潤米褐
    'accent': '#A8B5C0',       # 淺霧藍
    'text_dark': '#5A5A5A',    # 深灰
    'text_light': '#8B8B8B',   # 中灰
    'bg_header': '#F5F3F0',    # 米白背景
    'success': '#88B8A8',      # 淺綠
    'error': '#C8A8A8',        # 淺粉紅
}

# 全域題庫
QUESTIONS = {'SAA': [], 'SAP': []}

def parse_options(raw_text):
    """解析選項（支援多種格式）"""
    opts = {}
    if not raw_text or raw_text == 'None':
        return opts
    
    # 支援 A. / A) / (A) 等多種格式
    for char in ['A', 'B', 'C', 'D']:
        patterns = [
            rf"{char}[.、:：)]\s*([^\r\n]+?)(?=\s*[ABCD][.、:：)]|$)",
            rf"[（(]{char}[）)]\s*([^\r\n]+?)(?=\s*[（(][ABCD][）)]|$)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, str(raw_text), re.DOTALL | re.IGNORECASE)
            if match:
                text = match.group(1).strip()
                text = ' '.join(text.split())  # 清理多餘空白
                if text:
                    opts[char] = text
                    break
        
        if char not in opts:
            opts[char] = ''
    
    return opts

def load_from_csv():
    """從 CSV 載入題庫"""
    files = {
        'SAA': 'AWS_SAA_繁體中文版.csv',
        'SAP': 'AWS_SAP_繁體中文版.csv'
    }
    
    print("\n" + "="*60)
    print("📚 開始載入題庫...")
    print("="*60)
    
    for cat, filename in files.items():
        if not os.path.exists(filename):
            print(f"⚠️  找不到檔案: {filename}")
            continue
        
        try:
            with open(filename, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                count = 0
                
                for row in reader:
                    # 至少要有一種語言的題目
                    if row.get('題目(英)') or row.get('題目(中)'):
                        q_data = {
                            'q_cn': row.get('題目(中)', '').strip(),
                            'q_en': row.get('題目(英)', '').strip(),
                            'ans': (row.get('正確答案', 'A').strip().upper() or 'A')[0],  # 只取第一個字元
                            'exp_cn': (row.get('解析(中)', '').strip() or 
                                      row.get('專業解析', '').strip() or 
                                      row.get('答案備註', '').strip() or 
                                      "暫無解析"),
                            'exp_en': (row.get('解析(英)', '').strip() or 
                                      row.get('答案備註', '').strip() or 
                                      "No explanation available"),
                            'opts_cn': parse_options(row.get('選項(中)', '')),
                            'opts_en': parse_options(row.get('選項(英)', ''))
                        }
                        
                        # 驗證至少有一種語言的完整資料
                        has_cn = q_data['q_cn'] and len(q_data['opts_cn']) >= 4
                        has_en = q_data['q_en'] and len(q_data['opts_en']) >= 4
                        
                        if has_cn or has_en:
                            QUESTIONS[cat].append(q_data)
                            count += 1
                
                print(f"✅ {cat}: 成功載入 {count} 題")
                
        except Exception as e:
            print(f"❌ {cat} 載入失敗: {e}")
    
    total = len(QUESTIONS['SAA']) + len(QUESTIONS['SAP'])
    print(f"\n📊 總計: {total} 題")
    print("="*60 + "\n")

load_from_csv()

def send_line(reply_token, messages):
    """發送 LINE 訊息"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    payload = {'replyToken': reply_token, 'messages': messages}
    response = requests.post(LINE_REPLY_URL, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"❌ LINE API 錯誤: {response.status_code}")

# ==================== Flex Message UI ====================

def welcome_flex():
    """歡迎畫面（含首次使用提示）"""
    return {
        "type": "flex",
        "altText": "AWS 證照練習助手",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "text",
                    "text": "AWS 證照練習助手",
                    "weight": "bold",
                    "color": COLORS['text_dark'],
                    "size": "xl",
                    "align": "center"
                }],
                "backgroundColor": COLORS['bg_header'],
                "paddingAll": "20px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "選擇考試科目",
                        "weight": "bold",
                        "size": "lg",
                        "color": COLORS['text_dark']
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "margin": "md",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "spacing": "sm",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "📘",
                                        "size": "md",
                                        "flex": 0
                                    },
                                    {
                                        "type": "text",
                                        "text": f"SAA 助理架構師｜{len(QUESTIONS['SAA'])} 題",
                                        "size": "sm",
                                        "color": COLORS['text_light'],
                                        "flex": 1
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "spacing": "sm",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "📗",
                                        "size": "md",
                                        "flex": 0
                                    },
                                    {
                                        "type": "text",
                                        "text": f"SAP 專業架構師｜{len(QUESTIONS['SAP'])} 題",
                                        "size": "sm",
                                        "color": COLORS['text_light'],
                                        "flex": 1
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "text",
                                "text": "💡 貼心提醒",
                                "size": "xs",
                                "color": COLORS['text_dark'],
                                "weight": "bold"
                            },
                            {
                                "type": "text",
                                "text": "本服務部署於免費雲端平台，首次開啟可能需要 15 秒熱機時間，若無反應請稍候片刻再試。",
                                "size": "xxs",
                                "color": COLORS['text_light'],
                                "wrap": True,
                                "margin": "sm"
                            },
                            {
                                "type": "text",
                                "text": "💬 隨時傳送任意訊息可返回主選單",
                                "size": "xxs",
                                "color": COLORS['accent'],
                                "wrap": True,
                                "margin": "xs"
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": COLORS['primary'],
                        "action": {
                            "type": "postback",
                            "label": "📘 SAA 助理架構師",
                            "data": "menu=lang&type=SAA"
                        },
                        "height": "sm"
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "color": COLORS['secondary'],
                        "action": {
                            "type": "postback",
                            "label": "📗 SAP 專業架構師",
                            "data": "menu=lang&type=SAP"
                        },
                        "height": "sm"
                    }
                ]
            }
        }
    }

def lang_select_flex(exam_type):
    """語言選擇畫面"""
    exam_name = {
        'SAA': 'Solutions Architect Associate',
        'SAP': 'Solutions Architect Professional'
    }
    
    return {
        "type": "flex",
        "altText": "選擇語言",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "text",
                    "text": exam_name[exam_type],
                    "weight": "bold",
                    "color": COLORS['text_dark'],
                    "size": "md",
                    "wrap": True
                }],
                "backgroundColor": COLORS['bg_header']
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"📚 題庫共 {len(QUESTIONS[exam_type])} 題",
                        "size": "sm",
                        "color": COLORS['text_light']
                    },
                    {
                        "type": "separator",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": "請選擇答題語言",
                        "margin": "md",
                        "color": COLORS['text_dark'],
                        "size": "sm"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": COLORS['primary'],
                        "action": {
                            "type": "postback",
                            "label": "🇹🇼 繁體中文",
                            "data": f"action=start&lang=cn&type={exam_type}"
                        },
                        "height": "sm"
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "color": COLORS['accent'],
                        "action": {
                            "type": "postback",
                            "label": "🇺🇸 English",
                            "data": f"action=start&lang=en&type={exam_type}"
                        },
                        "height": "sm"
                    }
                ]
            }
        }
    }

def question_flex(cat, lang, idx):
    """題目顯示畫面（優化排版）"""
    q = QUESTIONS[cat][idx]
    title = q['q_cn'] if (lang == 'cn' and q['q_cn']) else q['q_en']
    opts = q['opts_cn'] if (lang == 'cn' and q['opts_cn']) else q['opts_en']
    
    # 選項內容（關鍵：使用 wrap 防止文字被截斷）
    opt_contents = []
    for char in ['A', 'B', 'C', 'D']:
        if opts.get(char):
            opt_contents.append({
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "margin": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{char}.",
                        "size": "sm",
                        "color": COLORS['primary'],
                        "weight": "bold",
                        "flex": 0
                    },
                    {
                        "type": "text",
                        "text": opts[char],
                        "size": "sm",
                        "color": COLORS['text_dark'],
                        "wrap": True,
                        "flex": 1
                    }
                ]
            })
    
    lang_emoji = "🇹🇼" if lang == 'cn' else "🇺🇸"
    
    return {
        "type": "flex",
        "altText": f"AWS {cat} 練習",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "text",
                    "text": f"{lang_emoji} AWS {cat} 練習",
                    "size": "xs",
                    "color": COLORS['text_light']
                }]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": title,
                        "wrap": True,
                        "weight": "bold",
                        "size": "md",
                        "color": COLORS['text_dark']
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": opt_contents
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": COLORS['primary'],
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": char,
                            "data": f"ans={char}&c={q['ans']}&id={idx}&l={lang}&t={cat}"
                        }
                    } for char in ['A', 'B', 'C', 'D']
                ]
            }
        }
    }

def result_flex(is_correct, correct_ans, explain, lang, cat):
    """答題結果畫面"""
    if is_correct:
        result_text = "🎉 答對了！"
        result_color = COLORS['success']
    else:
        result_text = f"💭 答錯了"
        result_color = COLORS['error']
    
    return {
        "type": "flex",
        "altText": "答題結果",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": result_text,
                        "weight": "bold",
                        "size": "lg",
                        "color": result_color
                    },
                    {
                        "type": "text",
                        "text": f"{'正確答案' if lang == 'cn' else 'Correct Answer'}: {correct_ans}",
                        "size": "sm",
                        "color": COLORS['text_dark'],
                        "margin": "sm"
                    },
                    {
                        "type": "separator",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": f"💡 {'解析' if lang == 'cn' else 'Explanation'}",
                        "size": "xs",
                        "color": COLORS['text_dark'],
                        "weight": "bold",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": explain,
                        "size": "xs",
                        "color": COLORS['text_light'],
                        "wrap": True,
                        "margin": "sm"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": COLORS['primary'],
                        "action": {
                            "type": "postback",
                            "label": "➡️ 下一題" if lang == 'cn' else "➡️ Next",
                            "data": f"action=start&lang={lang}&type={cat}"
                        },
                        "height": "sm"
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "postback",
                            "label": "🏠 主選單" if lang == 'cn' else "🏠 Menu",
                            "data": "menu=main"
                        },
                        "height": "sm"
                    }
                ]
            }
        }
    }

# ==================== 路由處理 ====================

@app.route("/")
def home():
    """首頁"""
    return f"""
    <html>
    <head><title>AWS LINE Bot</title></head>
    <body style="font-family: Arial; padding: 20px; background: #f5f5f5;">
        <h1 style="color: {COLORS['primary']}">✅ AWS 證照練習助手</h1>
        <p>📚 SAA 題庫：{len(QUESTIONS['SAA'])} 題</p>
        <p>📚 SAP 題庫：{len(QUESTIONS['SAP'])} 題</p>
        <p>🔗 <a href="https://line.me/R/ti/p/@your-bot-id">加入 LINE 好友</a></p>
    </body>
    </html>
    """

@app.route("/callback", methods=['POST'])
def callback():
    """處理 LINE Webhook"""
    events = request.json.get('events', [])
    
    for event in events:
        tk = event.get('replyToken')
        
        # 加好友或傳送訊息 → 顯示主選單
        if event['type'] in ['message', 'follow']:
            send_line(tk, [welcome_flex()])
        
        # Postback 事件處理
        elif event['type'] == 'postback':
            data = parse_qs(event['postback']['data'])
            
            # 選擇語言
            if data.get('menu', [None])[0] == 'lang':
                send_line(tk, [lang_select_flex(data['type'][0])])
            
            # 開始出題
            elif data.get('action', [None])[0] == 'start':
                lang = data['lang'][0]
                cat = data['type'][0]
                
                # 過濾出有對應語言內容的題目
                pool = [i for i, q in enumerate(QUESTIONS[cat]) 
                       if (q['q_cn'] if lang == 'cn' else q['q_en'])]
                
                if not pool:
                    send_line(tk, [{
                        "type": "text",
                        "text": f"❌ {cat} {'中文' if lang == 'cn' else '英文'}題庫目前沒有題目"
                    }])
                else:
                    send_line(tk, [question_flex(cat, lang, random.choice(pool))])
            
            # 答題判斷
            elif 'ans' in data:
                user_ans = data['ans'][0]
                correct_ans = data['c'][0]
                q_idx = int(data['id'][0])
                lang = data['l'][0]
                cat = data['t'][0]
                
                q = QUESTIONS[cat][q_idx]
                explain = q['exp_cn'] if lang == 'cn' else q['exp_en']
                is_correct = (user_ans == correct_ans)
                
                send_line(tk, [result_flex(is_correct, correct_ans, explain, lang, cat)])
            
            # 返回主選單
            elif data.get('menu', [None])[0] == 'main':
                send_line(tk, [welcome_flex()])
    
    return 'OK'

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
