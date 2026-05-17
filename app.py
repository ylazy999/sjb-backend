from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import hmac
import hashlib
import base64
import json
import time
import threading
import sqlite3
import os
from datetime import datetime
from urllib.parse import urlencode, urlparse
import websocket
import ssl
from wsgiref.handlers import format_date_time

app = Flask(__name__)
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), 'user.db')

# Railway 环境变量
PORT = int(os.environ.get("PORT", 5000))
RAILWAY_STATIC_URL = os.environ.get("RAILWAY_STATIC_URL", "")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         username TEXT UNIQUE NOT NULL,
         password TEXT NOT NULL,
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS admins
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         username TEXT UNIQUE NOT NULL,
         password TEXT NOT NULL,
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor = conn.execute("SELECT COUNT(*) FROM admins")
    if cursor.fetchone()[0] == 0:
        conn.execute("INSERT INTO admins (username, password) VALUES ('admin', 'admin123')")
    conn.commit()
    conn.close()

init_db()

# ========== 用户管理API ==========

@app.route('/api/users/login', methods=['POST'])
def user_login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    conn = get_db()
    cursor = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return jsonify({
            "success": True,
            "msg": "登录成功",
            "user_id": user['id'],
            "username": user['username']
        })
    return jsonify({"success": False, "msg": "账号或密码错误"}), 401

@app.route('/api/users/list', methods=['POST'])
def list_users():
    data = request.get_json()
    admin_name = data.get('admin_name', '')
    admin_pwd = data.get('admin_pwd', '')
    
    conn = get_db()
    cursor = conn.execute("SELECT * FROM admins WHERE username=? AND password=?", (admin_name, admin_pwd))
    admin = cursor.fetchone()
    
    if not admin:
        conn.close()
        return jsonify({"success": False, "msg": "管理员验证失败"}), 401
    
    cursor = conn.execute("SELECT id, username, created_at FROM users ORDER BY created_at DESC")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({"success": True, "users": users})

@app.route('/api/users/add', methods=['POST'])
def add_user():
    data = request.get_json()
    admin_name = data.get('admin_name', '')
    admin_pwd = data.get('admin_pwd', '')
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    conn = get_db()
    cursor = conn.execute("SELECT * FROM admins WHERE username=? AND password=?", (admin_name, admin_pwd))
    admin = cursor.fetchone()
    
    if not admin:
        conn.close()
        return jsonify({"success": False, "msg": "管理员验证失败"}), 401
    
    if not username or not password:
        conn.close()
        return jsonify({"success": False, "msg": "账号密码不能为空"}), 400
    
    try:
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "msg": "添加成功"})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "msg": "账号已存在"}), 400

@app.route('/api/users/delete', methods=['POST'])
def delete_user():
    data = request.get_json()
    admin_name = data.get('admin_name', '')
    admin_pwd = data.get('admin_pwd', '')
    user_id = data.get('user_id')
    
    conn = get_db()
    cursor = conn.execute("SELECT * FROM admins WHERE username=? AND password=?", (admin_name, admin_pwd))
    admin = cursor.fetchone()
    
    if not admin:
        conn.close()
        return jsonify({"success": False, "msg": "管理员验证失败"}), 401
    
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "msg": "删除成功"})

# ========== 讯飞星火API ==========

SPARK_API_CONFIG = {
    "app_id": "2e0abaca",
    "api_secret": "OTgwYjBjYmYzYmMwZjg0ZjUxZWlyYTdl",
    "api_key": "d3a698db98a3ffc6234cb48b84f272c9",
    "api_version": "v3.5",
    "domain": "generalv3.5",
    "url": "wss://spark-api.xf-yun.com/v3.5/chat"
}

conversation_history = {}

def get_auth_url():
    api_key = SPARK_API_CONFIG["api_key"]
    api_secret = SPARK_API_CONFIG["api_secret"]
    url = SPARK_API_CONFIG["url"]
    
    parse_result = urlparse(url)
    host = parse_result.netloc
    path = parse_result.path
    
    date = format_date_time(time.time())
    signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
    signature_sha = hmac.new(api_secret.encode('utf-8'), signature_origin.encode('utf-8'), digestmod=hashlib.sha256).digest()
    signature_sha_base64 = base64.b64encode(signature_sha).decode(encoding='utf-8')
    authorization_origin = f'api_key="{api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_base64}"'
    authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
    
    v = {
        "authorization": authorization,
        "date": date,
        "host": host
    }
    url = url + '?' + urlencode(v)
    
    return url

class SparkMessageHandler:
    def __init__(self):
        self.response = ""
        self.completed = False
        self.error = None

    def on_message(self, ws, message):
        data = json.loads(message)
        code = data['header']['code']
        
        if code != 0:
            self.error = data['header']['message']
            self.completed = True
            return
        
        choices = data['payload']['choices']
        status = choices['status']
        
        for content in choices['text']:
            self.response += content['content']
        
        if status == 2:
            self.completed = True

    def on_error(self, ws, error):
        self.error = str(error)
        self.completed = True

    def on_close(self, ws, close_status_code, close_msg):
        self.completed = True

    def on_open(self, ws):
        pass

def call_spark_api(messages):
    handler = SparkMessageHandler()
    
    try:
        ws_url = get_auth_url()
        
        request_data = {
            "header": {
                "app_id": SPARK_API_CONFIG["app_id"],
                "uid": "qiuqiu_user"
            },
            "parameter": {
                "chat": {
                    "domain": SPARK_API_CONFIG["domain"],
                    "temperature": 0.7,
                    "max_tokens": 2048,
                    "top_k": 4
                }
            },
            "payload": {
                "message": {
                    "text": messages
                }
            }
        }
        
        ws = websocket.WebSocketApp(
            ws_url,
            on_message=handler.on_message,
            on_error=handler.on_error,
            on_close=handler.on_close
        )
        
        ws.on_open = lambda ws: ws.send(json.dumps(request_data))
        
        wst = threading.Thread(target=ws.run_forever)
        wst.daemon = True
        wst.start()
        
        timeout = 30
        start_time = time.time()
        while not handler.completed and time.time() - start_time < timeout:
            time.sleep(0.1)
        
        if handler.error:
            return {"success": False, "error": handler.error}
        
        return {"success": True, "response": handler.response}
    
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.route('/api/qiuqiu/chat', methods=['POST'])
def chat_with_qiuqiu():
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        user_id = data.get('user_id', 'default')
        
        if not user_message:
            return jsonify({"success": False, "error": "消息不能为空"}), 400
        
        if user_id not in conversation_history:
            conversation_history[user_id] = [
                {
                    "role": "system",
                    "content": "你是球球，一个专业的体育赛事分析师。你的任务是帮助用户分析体育比赛、预测结果、解读球队数据等。请用友好、专业的语气回答用户的问题。"
                }
            ]
        
        conversation_history[user_id].append({
            "role": "user",
            "content": user_message
        })
        
        result = call_spark_api(conversation_history[user_id])
        
        if result['success']:
            conversation_history[user_id].append({
                "role": "assistant",
                "content": result['response']
            })
            
            if len(conversation_history[user_id]) > 20:
                conversation_history[user_id] = conversation_history[user_id][:1] + conversation_history[user_id][-18:]
            
            return jsonify({
                "success": True,
                "response": result['response'],
                "timestamp": datetime.now().strftime("%H:%M")
            })
        else:
            return jsonify({
                "success": False,
                "error": result['error']
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/qiuqiu/analyze-match', methods=['POST'])
def analyze_match():
    try:
        data = request.get_json()
        home_team = data.get('home_team', '')
        away_team = data.get('away_team', '')
        match_info = data.get('match_info', '')
        
        prompt = f"""请作为专业的体育赛事分析师，分析这场比赛：

比赛：{home_team} vs {away_team}
附加信息：{match_info}

请从以下几个方面进行分析：
1. 双方球队近期状态
2. 历史交锋记录
3. 关键球员分析
4. 战术特点对比
5. 预测结果和比分建议

请用简洁专业的语言回答。"""
        
        messages = [
            {
                "role": "system",
                "content": "你是球球，一个专业的体育赛事分析师。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        result = call_spark_api(messages)
        
        if result['success']:
            return jsonify({
                "success": True,
                "analysis": result['response']
            })
        else:
            return jsonify({
                "success": False,
                "error": result['error']
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/qiuqiu/clear-history', methods=['POST'])
def clear_history():
    try:
        data = request.get_json()
        user_id = data.get('user_id', 'default')
        
        if user_id in conversation_history:
            del conversation_history[user_id]
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/')
def index():
    return jsonify({
        "message": "球球AI体育分析服务",
        "version": "1.0",
        "endpoints": {
            "user_login": "/api/users/login",
            "user_list": "/api/users/list",
            "user_add": "/api/users/add",
            "user_delete": "/api/users/delete",
            "chat": "/api/qiuqiu/chat",
            "analyze_match": "/api/qiuqiu/analyze-match",
            "clear_history": "/api/qiuqiu/clear-history"
        }
    })

if __name__ == '__main__':
    print("=" * 50)
    print("球球AI体育分析服务启动中...")
    print("=" * 50)
    print(f"服务地址: http://0.0.0.0:{PORT}")
    print(f"API文档: http://0.0.0.0:{PORT}/")
    print("=" * 50)
    app.run(host='0.0.0.0', port=PORT, debug=True)
