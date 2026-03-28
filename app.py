from flask import Flask, request
import requests
import os
import random
import re
from urllib.parse import parse_qs

app = Flask(__name__)

# LINE 設定
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
LINE_REPLY_URL = 'https://api.line.me/v2/bot/message/reply'

# 全域題庫：分為 SAA 和 SAP
QUESTIONS = {'SAA': [], 'SAP': []}

# 1. 從 Excel 載入題庫
def load_questions_from_excel():
    """從 Excel 檔案載入 SAA 和 SAP 題庫"""
    filename = 'AWS_SAA_SAP_繁體中文版.xlsx'
    
    if not os.path.exists(filename):
        print(f"⚠️ Excel 檔案不存在：{filename}")
        return load_default_questions()
    
    try:
        import openpyxl
        wb = openpyxl.load_workbook(filename, data_only=True)
        
        # 處理 SAA 和 SAP 兩個工作表
        for sheet_name in ['SAA', 'SAP']:
            if sheet_name not in wb.sheetnames:
                print(f"⚠️ 找不到工作表：{sheet_name}")
                continue
            
            sheet = wb[sheet_name]
            questions = []
            
            # 讀取標題列（第一列）
            headers = [cell.value for cell in sheet[1]]
            
            # 找出欄位索引
            col_map = {}
            for idx, header in enumerate(headers):
                if header:
                    header = str(header).strip()
                    col_map[header] = idx
            
            print(f"📋 {sheet_name} 工作表欄位：{list(col_map.keys())}")
            
            # 從第二列開始讀取資料
            for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    q_data = {
                        'q_cn': str(row[col_map.get('題目(中)', 0)] or '').strip(),
                        'q_en': str(row[col_map.get('題目(英)', 1)] or '').strip(),
                        'opt_cn_raw': str(row[col_map.get('選項(中)', 2)] or '').strip(),
                        'opt_en_raw': str(row[col_map.get('選項(英)', 3)] or '').strip(),
                        'ans': str(row[col_map.get('正確答案', 4)] or 'A').strip().upper(),
                        'exp_cn': str(row[col_map.get('解析(中)', 5)] or row[col_map.get('專業解析', 5)] or '暫無中文解析').strip(),
                        'exp_en': str(row[col_map.get('解析(英)', 6)] or 'No explanation available').strip()
                    }
                    
                    # 解析選項
                    q_data['opts_cn'] = parse_options(q_data['opt_cn_raw'])
                    q_data['opts_en'] = parse_options(q_data['opt_en_raw'])
                    
                    # 只有當題目和選項都有內容時才加入
                    if (q_data['q_cn'] or q_data['q_en']) and (q_data['opts_cn'].get('A') or q_data['opts_en'].get('A')):
                        questions.append(q_data)
                
                except Exception as e:
                    print(f"⚠️ {sheet_name} 第 {row_idx} 列解析失敗：{e}")
                    continue
            
            QUESTIONS[sheet_name] = questions
            print(f"✅ {sheet_name}：載入 {len(questions)} 題")
        
        wb.close()
        
        # 如果兩個都是空的，回傳預設題庫
        if len(QUESTIONS['SAA']) == 0 and len(QUESTIONS['SAP']) == 0:
            print("⚠️ Excel 解析後沒有題目，使用預設題庫")
            return load_default_questions()
        
        return QUESTIONS
        
    except ImportError:
        print("❌ 缺少 openpyxl 套件，請安裝：pip install openpyxl")
        return load_default_questions()
    except Exception as e:
        print(f"❌ Excel 載入失敗：{e}")
        return load_default_questions()

def parse_options(opt_raw):
    """解析選項文字"""
    opts = {}
    if not opt_raw:
        return {}
    
    # 支援多種格式：A. / A) / A /（A）
    for char in ['A', 'B', 'C', 'D']:
        patterns = [
            rf"{char}[.)\s](.*?)(?=[A-D][.)\s]|$)",  # A. 或 A) 或 A 
            rf"[（(]{char}[）)](.*?)(?=[（(][A-D][）)]|$)"  # （A）
        ]
        
        for pattern in patterns:
            match = re.search(pattern, opt_raw, re.DOTALL | re.IGNORECASE)
            if match:
                opts[char] = match.group(1).strip()
                break
        
        # 如果還是沒找到，就留空
        if char not in opts:
            opts[char] = ""
    
    return opts

def load_default_questions():
    """預設題庫（當 Excel 載入失敗時使用）"""
    return {
        'SAA': [
            {
                'q_cn': '某公司需要在AWS上部署一個需要處理突發流量的網站，但預算有限。以下哪種EC2購買選項最適合？',
                'q_en': 'A company needs to deploy a website on AWS that can handle traffic spikes with a limited budget. Which EC2 purchasing option is most suitable?',
                'opts_cn': {
                    'A': 'On-Demand Instances',
                    'B': 'Reserved Instances',
                    'C': 'Spot Instances',
                    'D': 'Savings Plans'
                },
                'opts_en': {
                    'A': 'On-Demand Instances',
                    'B': 'Reserved Instances',
                    'C': 'Spot Instances',
                    'D': 'Savings Plans'
                },
                'ans': 'C',
                'exp_cn': 'Spot Instances 可以以更低的價格使用未使用的 EC2 容量，最適合突發流量且預算有限的場景。',
                'exp_en': 'Spot Instances allow you to use spare EC2 capacity at a lower price, ideal for handling traffic spikes with limited budget.'
            }
        ],
        'SAP': [
            {
                'q_cn': '企業需要設計一個跨多個AWS區域的災難恢復方案，RTO要求小於1小時。最適合的策略是？',
                'q_en': 'An enterprise needs to design a disaster recovery solution across multiple AWS regions with RTO < 1 hour. What is the most suitable strategy?',
                'opts_cn': {
                    'A': 'Backup and Restore',
                    'B': 'Pilot Light',
                    'C': 'Warm Standby',
                    'D': 'Multi-Site Active-Active'
                },
                'opts_en': {
                    'A': 'Backup and Restore',
                    'B': 'Pilot Light',
                    'C': 'Warm Standby',
                    'D': 'Multi-Site Active-Active'
                },
                'ans': 'C',
                'exp_cn': 'Warm Standby 策略在備援區域維持縮小版本的完整環境，可以快速擴展以滿足 RTO < 1小時的要求。',
                'exp_en': 'Warm Standby maintains a scaled-down version of a fully functional environment in the DR region, which can be quickly scaled up to meet RTO < 1 hour requirements.'
            }
        ]
    }

# 初始化載入題庫
load_questions_from_excel()
print(f"📚 題庫載入完成 - SAA: {len(QUESTIONS['SAA'])} 題, SAP: {len(QUESTIONS['SAP'])} 題")

# 2. 隨機抽題邏輯
def get_random_q(exam_type, lang):
    """根據考試類型和語言隨機抽題"""
    pool = QUESTIONS.get(exam_type, [])
    
    if not pool:
        return None
    
    # 過濾出有對應語言內容的題目
    if lang == 'cn':
        valid_indices = [i for i, q in enumerate(pool) if q['q_cn'] and q['opts_cn'].get('A')]
    else:
        valid_indices = [i for i, q in enumerate(pool) if q['q_en'] and q['opts_en'].get('A')]
    
    if not valid_indices:
        return None
    
    return random.choice(valid_indices)

def send_line(reply_token, messages):
    """發送 LINE 訊息"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
    }
    payload = {
        'replyToken': reply_token,
        'messages': messages
    }
    response = requests.post(LINE_REPLY_URL, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"❌ LINE API 錯誤：{response.status_code} - {response.text}")

# 3. Flex Message 介面
def welcome_flex():
    """歡迎畫面"""
    return {
        "type": "flex",
        "altText": "AWS 助手",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "text",
                    "text": "🎓 AWS 證照練習助手",
                    "weight": "bold",
                    "color": "#E67E22",
                    "size": "xl"
                }]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "準備好要挑戰了嗎？",
                        "weight": "bold",
                        "size": "md"
                    },
                    {
                        "type": "text",
                        "text": f"📚 題庫統計\nSAA: {len(QUESTIONS['SAA'])} 題\nSAP: {len(QUESTIONS['SAP'])} 題",
                        "wrap": True,
                        "size": "sm",
                        "color": "#555555",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": "💡 首次使用可能有 15 秒熱機時間",
                        "wrap": True,
                        "size": "xs",
                        "color": "#888888",
                        "margin": "md"
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
                        "color": "#3498DB",
                        "action": {
                            "type": "postback",
                            "label": "📘 SAA (Solutions Architect Associate)",
                            "data": "menu=lang&type=SAA"
                        }
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#E74C3C",
                        "action": {
                            "type": "postback",
                            "label": "📗 SAP (Solutions Architect Professional)",
                            "data": "menu=lang&type=SAP"
                        }
                    }
                ]
            }
        }
    }

def lang_select_flex(exam_type):
    """語言選擇畫面"""
    type_name = "Solutions Architect Associate" if exam_type == "SAA" else "Solutions Architect Professional"
    question_count = len(QUESTIONS.get(exam_type, []))
    
    return {
        "type": "flex",
        "altText": "選擇語言",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"📋 {type_name}",
                        "weight": "bold",
                        "size": "md"
                    },
                    {
                        "type": "text",
                        "text": f"題庫共 {question_count} 題",
                        "size": "sm",
                        "color": "#888888",
                        "margin": "sm"
                    },
                    {
                        "type": "separator",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": "請選擇答題語言：",
                        "margin": "md"
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
                        "color": "#27AE60",
                        "action": {
                            "type": "postback",
                            "label": "🇹🇼 繁體中文",
                            "data": f"action=start&lang=cn&type={exam_type}"
                        }
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#2980B9",
                        "action": {
                            "type": "postback",
                            "label": "🇺🇸 English",
                            "data": f"action=start&lang=en&type={exam_type}"
                        }
                    }
                ]
            }
        }
    }

def question_flex(exam_type, idx, lang):
    """題目顯示畫面"""
    q = QUESTIONS[exam_type][idx]
    title = q['q_cn'] if lang == 'cn' else q['q_en']
    opts = q['opts_cn'] if lang == 'cn' else q['opts_en']
    
    # 建立選項文字
    option_texts = []
    for char in ['A', 'B', 'C', 'D']:
        if opts.get(char):
            option_texts.append({
                "type": "text",
                "text": f"{char}. {opts[char]}",
                "wrap": True,
                "size": "sm",
                "margin": "md"
            })
    
    lang_emoji = "🇹🇼" if lang == 'cn' else "🇺🇸"
    type_name = "SAA" if exam_type == "SAA" else "SAP"
    
    return {
        "type": "flex",
        "altText": "題目",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{lang_emoji} AWS {type_name} 練習",
                        "size": "xs",
                        "color": "#aaaaaa"
                    },
                    {
                        "type": "text",
                        "text": title,
                        "wrap": True,
                        "weight": "bold",
                        "margin": "md",
                        "size": "md"
                    },
                    {
                        "type": "separator",
                        "margin": "xl"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "contents": option_texts
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#3498DB",
                            "action": {
                                "type": "postback",
                                "label": "A",
                                "data": f"action=ans&user=A&correct={q['ans']}&idx={idx}&lang={lang}&type={exam_type}"
                            }
                        },
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#3498DB",
                            "action": {
                                "type": "postback",
                                "label": "B",
                                "data": f"action=ans&user=B&correct={q['ans']}&idx={idx}&lang={lang}&type={exam_type}"
                            }
                        },
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#3498DB",
                            "action": {
                                "type": "postback",
                                "label": "C",
                                "data": f"action=ans&user=C&correct={q['ans']}&idx={idx}&lang={lang}&type={exam_type}"
                            }
                        },
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#3498DB",
                            "action": {
                                "type": "postback",
                                "label": "D",
                                "data": f"action=ans&user=D&correct={q['ans']}&idx={idx}&lang={lang}&type={exam_type}"
                            }
                        }
                    ]
                }]
            }
        }
    }

@app.route("/")
def home():
    """首頁"""
    return f"✅ AWS LINE Bot 運行中！<br>SAA: {len(QUESTIONS['SAA'])} 題<br>SAP: {len(QUESTIONS['SAP'])} 題"

@app.route("/callback", methods=['POST'])
def callback():
    """處理 LINE Webhook"""
    events = request.json.get('events', [])
    
    for event in events:
        reply_token = event.get('replyToken')
        
        # 加好友或傳送文字訊息
        if event['type'] == 'follow' or (event['type'] == 'message' and event['message']['type'] == 'text'):
            send_line(reply_token, [welcome_flex()])
        
        # Postback 事件
        elif event['type'] == 'postback':
            data = parse_qs(event['postback']['data'])
            action = data.get('action', [None])[0]
            lang = data.get('lang', ['cn'])[0]
            exam_type = data.get('type', ['SAA'])[0]
            
            # 選擇語言
            if data.get('menu', [None])[0] == 'lang':
                send_line(reply_token, [lang_select_flex(exam_type)])
            
            # 開始答題
            elif action == 'start':
                idx = get_random_q(exam_type, lang)
                if idx is not None:
                    send_line(reply_token, [question_flex(exam_type, idx, lang)])
                else:
                    send_line(reply_token, [{
                        "type": "text",
                        "text": f"❌ 抱歉，{exam_type} 的{'中文' if lang == 'cn' else '英文'}題庫目前沒有題目。"
                    }])
            
            # 回答問題
            elif action == 'ans':
                user_ans = data.get('user', [''])[0]
                correct_ans = data.get('correct', [''])[0]
                q_idx = int(data.get('idx', ['0'])[0])
                
                q = QUESTIONS[exam_type][q_idx]
                explain = q['exp_cn'] if lang == 'cn' else q['exp_en']
                
                if user_ans == correct_ans:
                    result = "🎉 答對了！"
                    result_color = "#27AE60"
                else:
                    result = f"❌ 答錯了"
                    result_color = "#E74C3C"
                
                send_line(reply_token, [
                    {
                        "type": "text",
                        "text": f"{result}\n{'正確答案' if lang == 'cn' else 'Correct Answer'}: {correct_ans}\n\n💡 {'解析' if lang == 'cn' else 'Explanation'}:\n{explain}"
                    },
                    {
                        "type": "flex",
                        "altText": "下一步",
                        "contents": {
                            "type": "bubble",
                            "size": "micro",
                            "body": {
                                "type": "box",
                                "layout": "vertical",
                                "spacing": "sm",
                                "contents": [
                                    {
                                        "type": "button",
                                        "style": "primary",
                                        "color": "#3498DB",
                                        "action": {
                                            "type": "postback",
                                            "label": "➡️ 下一題" if lang == 'cn' else "➡️ Next Question",
                                            "data": f"action=start&lang={lang}&type={exam_type}"
                                        }
                                    },
                                    {
                                        "type": "button",
                                        "style": "secondary",
                                        "action": {
                                            "type": "postback",
                                            "label": "🏠 回主選單" if lang == 'cn' else "🏠 Main Menu",
                                            "data": "menu=main"
                                        }
                                    }
                                ]
                            }
                        }
                    }
                ])
            
            # 回主選單
            elif data.get('menu', [None])[0] == 'main':
                send_line(reply_token, [welcome_flex()])
    
    return 'OK'

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
