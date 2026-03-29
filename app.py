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

# 莫蘭迪配色
COLORS = {
    'primary': '#8B9D83',
    'secondary': '#B4A7A3',
    'accent': '#9E9FA5',
    'success': '#8FA87F',
    'error': '#C8A8A0',
    'saa': '#7C9885',
    'sap': '#A98E8F',
}

QUESTIONS = {'SAA': [], 'SAP': []}

def load_questions_from_excel():
    """從 Excel 載入題庫（修正版：支援任何工作表名稱）"""
    filename = 'AWS_SAA_SAP_繁體中文版.xlsx'
    
    print(f"🔍 開始載入 Excel：{filename}")
    
    if not os.path.exists(filename):
        print(f"❌ 檔案不存在：{filename}")
        print(f"📂 當前目錄檔案：{os.listdir('.')}")
        return load_default_questions()
    
    try:
        import openpyxl
        print("✅ openpyxl 套件載入成功")
        
        wb = openpyxl.load_workbook(filename, data_only=True)
        print(f"✅ Excel 檔案開啟成功")
        print(f"📋 工作表列表：{wb.sheetnames}")
        
        # 處理每個工作表
        for sheet_name in wb.sheetnames:
            # 判斷是 SAA 還是 SAP（只要名稱包含就可以）
            if 'SAA' in sheet_name.upper():
                exam_type = 'SAA'
            elif 'SAP' in sheet_name.upper():
                exam_type = 'SAP'
            else:
                print(f"⚠️ 跳過工作表（無法判斷類型）：{sheet_name}")
                continue
            
            print(f"\n{'='*60}")
            print(f"📖 處理工作表：{sheet_name} → {exam_type}")
            print(f"{'='*60}")
            
            sheet = wb[sheet_name]
            questions = []
            
            # 讀取標題列
            headers = []
            for cell in sheet[1]:
                if cell.value:
                    headers.append(str(cell.value).strip())
                else:
                    headers.append('')
            
            print(f"📝 欄位列表（共 {len(headers)} 欄）：")
            for i, h in enumerate(headers[:10]):
                print(f"   [{i}] {h}")
            
            # 建立欄位映射（更智能的匹配）
            col_map = {}
            for idx, header in enumerate(headers):
                h_lower = header.lower()
                
                # 題目欄位
                if '題目' in h_lower or 'question' in h_lower:
                    if '中' in h_lower or '繁' in h_lower or 'cn' in h_lower or 'chinese' in h_lower:
                        col_map['q_cn'] = idx
                        print(f"   ✓ 找到中文題目欄位：[{idx}] {header}")
                    elif '英' in h_lower or 'en' in h_lower or 'english' in h_lower:
                        col_map['q_en'] = idx
                        print(f"   ✓ 找到英文題目欄位：[{idx}] {header}")
                
                # 選項欄位
                elif '選項' in h_lower or 'option' in h_lower or 'choice' in h_lower:
                    if '中' in h_lower or '繁' in h_lower or 'cn' in h_lower or 'chinese' in h_lower:
                        col_map['opt_cn'] = idx
                        print(f"   ✓ 找到中文選項欄位：[{idx}] {header}")
                    elif '英' in h_lower or 'en' in h_lower or 'english' in h_lower:
                        col_map['opt_en'] = idx
                        print(f"   ✓ 找到英文選項欄位：[{idx}] {header}")
                
                # 答案欄位
                elif '答案' in h_lower or 'answer' in h_lower or '正確' in h_lower:
                    col_map['ans'] = idx
                    print(f"   ✓ 找到答案欄位：[{idx}] {header}")
                
                # 解析欄位
                elif '解析' in h_lower or 'explanation' in h_lower or '說明' in h_lower:
                    if '中' in h_lower or '繁' in h_lower or 'cn' in h_lower or 'chinese' in h_lower or '專業' in h_lower:
                        col_map['exp_cn'] = idx
                        print(f"   ✓ 找到中文解析欄位：[{idx}] {header}")
                    elif '英' in h_lower or 'en' in h_lower or 'english' in h_lower:
                        col_map['exp_en'] = idx
                        print(f"   ✓ 找到英文解析欄位：[{idx}] {header}")
            
            print(f"\n📊 欄位映射結果：{col_map}")
            
            # 檢查必要欄位
            if 'ans' not in col_map:
                print(f"❌ 找不到「答案」欄位，跳過此工作表")
                continue
            
            # 讀取資料
            success_count = 0
            failed_count = 0
            
            for row_idx in range(2, sheet.max_row + 1):
                try:
                    row = list(sheet[row_idx])
                    
                    # 提取資料（使用 get 避免 KeyError）
                    q_data = {
                        'q_cn': str(row[col_map['q_cn']].value or '').strip() if 'q_cn' in col_map else '',
                        'q_en': str(row[col_map['q_en']].value or '').strip() if 'q_en' in col_map else '',
                        'opt_cn_raw': str(row[col_map['opt_cn']].value or '').strip() if 'opt_cn' in col_map else '',
                        'opt_en_raw': str(row[col_map['opt_en']].value or '').strip() if 'opt_en' in col_map else '',
                        'ans': str(row[col_map['ans']].value or 'A').strip().upper(),
                        'exp_cn': str(row[col_map['exp_cn']].value or '暫無中文解析').strip() if 'exp_cn' in col_map else '暫無中文解析',
                        'exp_en': str(row[col_map['exp_en']].value or 'No explanation available').strip() if 'exp_en' in col_map else 'No explanation available'
                    }
                    
                    # 只取答案的第一個字元（如果是 "A." 會變成 "A"）
                    if q_data['ans']:
                        q_data['ans'] = q_data['ans'][0]
                    
                    # 解析選項
                    q_data['opts_cn'] = parse_options(q_data['opt_cn_raw'])
                    q_data['opts_en'] = parse_options(q_data['opt_en_raw'])
                    
                    # 驗證：至少要有一種語言的完整內容
                    has_cn = q_data['q_cn'] and len(q_data['opts_cn']) >= 4
                    has_en = q_data['q_en'] and len(q_data['opts_en']) >= 4
                    
                    if has_cn or has_en:
                        questions.append(q_data)
                        success_count += 1
                        
                        # 顯示前 3 題的資料（除錯用）
                        if success_count <= 3:
                            print(f"\n   ✅ 第 {row_idx} 列解析成功：")
                            print(f"      中文題目：{q_data['q_cn'][:50]}...")
                            print(f"      英文題目：{q_data['q_en'][:50]}...")
                            print(f"      中文選項：{list(q_data['opts_cn'].keys())}")
                            print(f"      英文選項：{list(q_data['opts_en'].keys())}")
                            print(f"      正確答案：{q_data['ans']}")
                    else:
                        failed_count += 1
                        if failed_count <= 3:  # 只顯示前3個失敗的
                            print(f"\n   ⚠️ 第 {row_idx} 列跳過（內容不完整）：")
                            print(f"      中文題目：{q_data['q_cn'][:30] if q_data['q_cn'] else '無'}")
                            print(f"      中文選項數：{len(q_data['opts_cn'])}")
                
                except Exception as e:
                    failed_count += 1
                    if failed_count <= 3:
                        print(f"\n   ❌ 第 {row_idx} 列解析失敗：{e}")
            
            QUESTIONS[exam_type] = questions
            print(f"\n✅ {exam_type} 完成：成功 {success_count} 題，跳過 {failed_count} 題（總共 {sheet.max_row - 1} 列）")
        
        wb.close()
        
        # 統計
        total = len(QUESTIONS['SAA']) + len(QUESTIONS['SAP'])
        if total == 0:
            print("\n❌ Excel 解析後沒有任何題目，使用預設題庫")
            return load_default_questions()
        
        print(f"\n🎉 題庫載入完成！")
        print(f"📊 SAA: {len(QUESTIONS['SAA'])} 題")
        print(f"📊 SAP: {len(QUESTIONS['SAP'])} 題")
        print(f"📊 總計: {total} 題")
        
        return QUESTIONS
        
    except ImportError:
        print("❌ 缺少 openpyxl 套件")
        return load_default_questions()
    except Exception as e:
        print(f"❌ Excel 載入失敗：{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return load_default_questions()

def parse_options(opt_raw):
    """解析選項（強化版）"""
    opts = {}
    
    if not opt_raw or opt_raw == 'None' or len(opt_raw) < 5:
        return opts
    
    # 多種分隔符號支援
    for char in ['A', 'B', 'C', 'D']:
        # 嘗試多種格式
        patterns = [
            rf'{char}[.、:：)]\s*([^\r\n]+?)(?=\s*[ABCD][.、:：)]|$)',  # A. 或 A) 等
            rf'{char}\s+([^\r\n]+?)(?=\s*[ABCD]\s+|$)',                 # A 空格
            rf'[（(]{char}[）)]\s*([^\r\n]+?)(?=\s*[（(][ABCD][）)]|$)', # (A) 或 （A）
        ]
        
        found = False
        for pattern in patterns:
            match = re.search(pattern, opt_raw, re.DOTALL | re.IGNORECASE)
            if match:
                text = match.group(1).strip()
                # 移除可能的換行符和多餘空格
                text = ' '.join(text.split())
                if text and len(text) > 0:
                    opts[char] = text
                    found = True
                    break
        
        if not found:
            opts[char] = ''
    
    return opts

def load_default_questions():
    """預設題庫"""
    print("📚 載入預設題庫")
    return {
        'SAA': [
            {
                'q_cn': '某公司需要在AWS上部署一個需要處理突發流量的網站，但預算有限。以下哪種EC2購買選項最適合？',
                'q_en': 'A company needs to deploy a website on AWS that can handle traffic spikes with a limited budget. Which EC2 purchasing option is most suitable?',
                'opts_cn': {'A': 'On-Demand Instances', 'B': 'Reserved Instances', 'C': 'Spot Instances', 'D': 'Savings Plans'},
                'opts_en': {'A': 'On-Demand Instances', 'B': 'Reserved Instances', 'C': 'Spot Instances', 'D': 'Savings Plans'},
                'ans': 'C',
                'exp_cn': 'Spot Instances 可以以更低的價格使用未使用的 EC2 容量，最適合突發流量且預算有限的場景。',
                'exp_en': 'Spot Instances allow you to use spare EC2 capacity at a lower price, ideal for handling traffic spikes with limited budget.'
            },
            {
                'q_cn': '企業應用程序需要共享文件系統，可以同時被多個EC2實例訪問和修改。以下哪個AWS服務最適合？',
                'q_en': 'An enterprise application needs a shared file system that can be accessed and modified by multiple EC2 instances simultaneously. Which AWS service is most suitable?',
                'opts_cn': {'A': 'Amazon S3', 'B': 'Amazon EBS', 'C': 'Amazon EFS', 'D': 'AWS Storage Gateway'},
                'opts_en': {'A': 'Amazon S3', 'B': 'Amazon EBS', 'C': 'Amazon EFS', 'D': 'AWS Storage Gateway'},
                'ans': 'C',
                'exp_cn': 'Amazon EFS 提供完全託管的共享文件系統，支援多個 EC2 實例同時讀寫。',
                'exp_en': 'Amazon EFS provides a fully managed shared file system that supports concurrent read-write access from multiple EC2 instances.'
            }
        ],
        'SAP': [
            {
                'q_cn': '企業需要設計一個跨多個AWS區域的災難恢復方案，RTO要求小於1小時。最適合的策略是？',
                'q_en': 'An enterprise needs to design a disaster recovery solution across multiple AWS regions with RTO < 1 hour. What is the most suitable strategy?',
                'opts_cn': {'A': 'Backup and Restore', 'B': 'Pilot Light', 'C': 'Warm Standby', 'D': 'Multi-Site Active-Active'},
                'opts_en': {'A': 'Backup and Restore', 'B': 'Pilot Light', 'C': 'Warm Standby', 'D': 'Multi-Site Active-Active'},
                'ans': 'C',
                'exp_cn': 'Warm Standby 策略在備援區域維持縮小版本的完整環境，可以快速擴展以滿足 RTO < 1小時的要求。',
                'exp_en': 'Warm Standby maintains a scaled-down version of a fully functional environment in the DR region, which can be quickly scaled up to meet RTO < 1 hour requirements.'
            }
        ]
    }

# 初始化
print("\n" + "="*60)
print("🚀 AWS LINE Bot 啟動中...")
print("="*60)
load_questions_from_excel()
print("="*60 + "\n")

def get_random_q(exam_type, lang):
    """隨機抽題"""
    pool = QUESTIONS.get(exam_type, [])
    if not pool:
        return None
    
    if lang == 'cn':
        valid = [i for i, q in enumerate(pool) if q['q_cn'] and len(q.get('opts_cn', {})) >= 4]
    else:
        valid = [i for i, q in enumerate(pool) if q['q_en'] and len(q.get('opts_en', {})) >= 4]
    
    return random.choice(valid) if valid else None

def send_line(reply_token, messages):
    """發送訊息"""
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'}
    payload = {'replyToken': reply_token, 'messages': messages}
    response = requests.post(LINE_REPLY_URL, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"❌ LINE API Error: {response.status_code} - {response.text}")

# Flex Messages（莫蘭迪配色）
def welcome_flex():
    return {
        "type": "flex", "altText": "AWS 證照助手",
        "contents": {
            "type": "bubble",
            "header": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "AWS 證照練習助手", "weight": "bold", "color": COLORS['primary'], "size": "xl", "align": "center"}], "backgroundColor": "#F5F5F0"},
            "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": "準備好挑戰了嗎？", "weight": "bold", "size": "md", "color": "#5A5A5A"},
                {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
                    {"type": "text", "text": f"📚 SAA 題庫：{len(QUESTIONS['SAA'])} 題", "size": "sm", "color": "#6B6B6B"},
                    {"type": "text", "text": f"📚 SAP 題庫：{len(QUESTIONS['SAP'])} 題", "size": "sm", "color": "#6B6B6B"}
                ]}
            ]},
            "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                {"type": "button", "style": "primary", "color": COLORS['saa'], "action": {"type": "postback", "label": "📘 SAA 助理架構師", "data": "menu=lang&type=SAA"}},
                {"type": "button", "style": "primary", "color": COLORS['sap'], "action": {"type": "postback", "label": "📗 SAP 專業架構師", "data": "menu=lang&type=SAP"}}
            ]}
        }
    }

def lang_select_flex(exam_type):
    name = "Solutions Architect Associate" if exam_type == "SAA" else "Solutions Architect Professional"
    count = len(QUESTIONS.get(exam_type, []))
    color = COLORS['saa'] if exam_type == "SAA" else COLORS['sap']
    return {
        "type": "flex", "altText": "選擇語言",
        "contents": {
            "type": "bubble",
            "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": name, "weight": "bold", "size": "md", "color": color, "wrap": True},
                {"type": "text", "text": f"題庫共 {count} 題", "size": "sm", "color": "#888888", "margin": "sm"},
                {"type": "separator", "margin": "md"},
                {"type": "text", "text": "請選擇答題語言", "margin": "md", "color": "#5A5A5A"}
            ]},
            "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                {"type": "button", "style": "primary", "color": COLORS['primary'], "action": {"type": "postback", "label": "🇹🇼 繁體中文", "data": f"action=start&lang=cn&type={exam_type}"}},
                {"type": "button", "style": "primary", "color": COLORS['accent'], "action": {"type": "postback", "label": "🇺🇸 English", "data": f"action=start&lang=en&type={exam_type}"}}
            ]}
        }
    }

def question_flex(exam_type, idx, lang):
    q = QUESTIONS[exam_type][idx]
    title = q['q_cn'] if lang == 'cn' else q['q_en']
    opts = q['opts_cn'] if lang == 'cn' else q['opts_en']
    
    option_texts = []
    for char in ['A', 'B', 'C', 'D']:
        if opts.get(char):
            option_texts.append({"type": "text", "text": f"{char}. {opts[char]}", "wrap": True, "size": "sm", "color": "#5A5A5A", "margin": "md"})
    
    type_color = COLORS['saa'] if exam_type == "SAA" else COLORS['sap']
    
    return {
        "type": "flex", "altText": "題目",
        "contents": {
            "type": "bubble",
            "header": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": f"{'🇹🇼' if lang == 'cn' else '🇺🇸'} {exam_type} 練習", "size": "xs", "color": "#AAAAAA"}]},
            "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": title, "wrap": True, "weight": "bold", "size": "md", "color": type_color},
                {"type": "separator", "margin": "lg"},
                {"type": "box", "layout": "vertical", "margin": "lg", "contents": option_texts}
            ]},
            "footer": {"type": "box", "layout": "vertical", "contents": [{"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                {"type": "button", "style": "primary", "color": COLORS['secondary'], "action": {"type": "postback", "label": char, "data": f"action=ans&user={char}&correct={q['ans']}&idx={idx}&lang={lang}&type={exam_type}"}} for char in ['A', 'B', 'C', 'D']
            ]}]}
        }
    }

@app.route("/")
def home():
    return f"✅ AWS Bot 運行中<br>SAA: {len(QUESTIONS['SAA'])} 題<br>SAP: {len(QUESTIONS['SAP'])} 題"

@app.route("/callback", methods=['POST'])
def callback():
    events = request.json.get('events', [])
    for event in events:
        reply_token = event.get('replyToken')
        if event['type'] == 'follow' or (event['type'] == 'message' and event['message']['type'] == 'text'):
            send_line(reply_token, [welcome_flex()])
        elif event['type'] == 'postback':
            data = parse_qs(event['postback']['data'])
            action = data.get('action', [None])[0]
            lang = data.get('lang', ['cn'])[0]
            exam_type = data.get('type', ['SAA'])[0]
            
            if data.get('menu', [None])[0] == 'lang':
                send_line(reply_token, [lang_select_flex(exam_type)])
            elif action == 'start':
                idx = get_random_q(exam_type, lang)
                if idx is not None:
                    send_line(reply_token, [question_flex(exam_type, idx, lang)])
                else:
                    send_line(reply_token, [{"type": "text", "text": f"❌ {exam_type} {'中文' if lang == 'cn' else '英文'}題庫目前沒有題目"}])
            elif action == 'ans':
                user_ans = data.get('user', [''])[0]
                correct_ans = data.get('correct', [''])[0]
                q_idx = int(data.get('idx', ['0'])[0])
                q = QUESTIONS[exam_type][q_idx]
                explain = q['exp_cn'] if lang == 'cn' else q['exp_en']
                result = "🎉 答對了！" if user_ans == correct_ans else f"❌ 答錯了"
                send_line(reply_token, [
                    {"type": "text", "text": f"{result}\n{'正確答案' if lang == 'cn' else 'Answer'}: {correct_ans}\n\n💡 {explain}"},
                    {"type": "flex", "altText": "下一步", "contents": {"type": "bubble", "size": "micro", "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                        {"type": "button", "style": "primary", "color": COLORS['primary'], "action": {"type": "postback", "label": "➡️ 下一題", "data": f"action=start&lang={lang}&type={exam_type}"}},
                        {"type": "button", "style": "secondary", "action": {"type": "postback", "label": "🏠 主選單", "data": "menu=main"}}
                    ]}}}
                ])
            elif data.get('menu', [None])[0] == 'main':
                send_line(reply_token, [welcome_flex()])
    return 'OK'

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
```

---

## 🔑 關鍵修改

1. **工作表名稱匹配**：改用 `if 'SAA' in sheet_name.upper()` 來判斷，所以 `AWS_SAA_繁體中文版` 也能識別
2. **更智能的欄位匹配**：支援「題目(中)」、「題目(英)」等多種命名
3. **詳細的除錯輸出**：會顯示前3題的解析結果
4. **莫蘭迪配色**：柔和優雅的色調

---

## 📝 部署後觀察

部署後，查看 Render Logs，應該會看到：
```
✅ 找到中文題目欄位：[X] 題目(中)
✅ 找到英文題目欄位：[X] 題目(英)
...
✅ SAA 完成：成功 XXX 題
