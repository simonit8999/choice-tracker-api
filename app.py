from flask import Flask, request, jsonify
import sqlite3
import json
from datetime import datetime
import os

app = Flask(__name__)

# CORS для всех запросов
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

API_SECRET = os.environ.get('API_SECRET', 'choice_super_secret_key_2025')
DB_PATH = os.environ.get('DB_PATH', '/tmp/choice_data.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_seen TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_progress (user_id INTEGER PRIMARY KEY, current_streak INTEGER DEFAULT 0, best_streak INTEGER DEFAULT 0, total_days INTEGER DEFAULT 0, total_attempts INTEGER DEFAULT 0, achievements TEXT DEFAULT '{}', last_action TEXT, last_update TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS attempts_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, start_date TEXT, end_date TEXT, days_completed INTEGER, end_reason TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notification_settings (user_id INTEGER PRIMARY KEY, enabled INTEGER DEFAULT 0, reminder_hour INTEGER DEFAULT 20, reminder_minute INTEGER DEFAULT 0, timezone TEXT DEFAULT 'Europe/Moscow')''')
    c.execute('''CREATE TABLE IF NOT EXISTS premium_users (user_id INTEGER PRIMARY KEY, activated_at TEXT, plan TEXT DEFAULT 'premium')''')
    c.execute('''CREATE TABLE IF NOT EXISTS basic_users (user_id INTEGER PRIMARY KEY, activated_at TEXT, plan TEXT DEFAULT 'basic')''')
    c.execute('''CREATE TABLE IF NOT EXISTS customers
                 (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
                  purchased_at TEXT, plan TEXT, amount INTEGER, status TEXT,
                  platega_invoice_id TEXT)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return jsonify({"status": "online", "app": "CHOICE Tracker API", "version": "1.0"})

@app.route('/api/sync', methods=['POST', 'OPTIONS'])
def sync_data():
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data"}), 400
            
        user_id = data.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        
        conn = get_db()
        c = conn.cursor()
        
        c.execute('''INSERT OR REPLACE INTO users (user_id, username, first_name, last_seen)
                     VALUES (?, ?, ?, ?)''',
                  (user_id, data.get('username', ''), data.get('first_name', ''), datetime.now().isoformat()))
        
        progress = data.get('progress', {})
        achievements = data.get('achievements', {})
        
        c.execute('''INSERT OR REPLACE INTO user_progress
                     (user_id, current_streak, best_streak, total_days, total_attempts, achievements, last_update)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, progress.get('current_streak', 0), progress.get('best_streak', 0),
                   progress.get('total_days', 0), progress.get('total_attempts', 0),
                   json.dumps(achievements), datetime.now().isoformat()))
        
        notification = data.get('notification_settings')
        if notification:
            c.execute('''INSERT OR REPLACE INTO notification_settings
                         (user_id, enabled, reminder_hour, reminder_minute, timezone)
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id, 1 if notification.get('enabled') else 0,
                       int(notification.get('hour', 20)), int(notification.get('minute', 0)),
                       notification.get('timezone', 'Europe/Moscow')))
        
        conn.commit()
        conn.close()
        
        return jsonify({"status": "ok", "message": "Data synced"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/load/<int:user_id>')
def load_data(user_id):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM user_progress WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        c.execute('SELECT * FROM notification_settings WHERE user_id = ?', (user_id,))
        notif = c.fetchone()
        conn.close()
        
        result = {"status": "ok", "data": None}
        if row:
            result["data"] = {
                "progress": {"current_streak": row['current_streak'], "best_streak": row['best_streak'], "total_days": row['total_days']},
                "achievements": json.loads(row['achievements'])
            }
        if notif:
            if result["data"] is None:
                result["data"] = {}
            result["data"]["notification"] = {
                "enabled": bool(notif['enabled']),
                "hour": notif['reminder_hour'],
                "minute": notif['reminder_minute'],
                "timezone": notif['timezone']
            }
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/notifications')
def get_notifications():
    """Отдаёт список пользователей с включёнными уведомлениями"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT user_id, reminder_hour, reminder_minute, timezone FROM notification_settings WHERE enabled = 1')
        users = []
        for r in c.fetchall():
            users.append({
                "user_id": r['user_id'],
                "hour": r['reminder_hour'],
                "minute": r['reminder_minute'],
                "timezone": r['timezone']
            })
        conn.close()
        return jsonify({"status": "ok", "users": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/api/check-access/<int:user_id>')
def check_access(user_id):
    """Проверяет есть ли у пользователя доступ"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT user_id FROM premium_users WHERE user_id = ?', (user_id,))
        premium = c.fetchone()
        c.execute('SELECT user_id FROM basic_users WHERE user_id = ?', (user_id,))
        basic = c.fetchone()
        conn.close()
        
        return jsonify({
            "has_access": premium is not None or basic is not None,
            "plan": "premium" if premium else ("basic" if basic else None)
        })
    except Exception as e:
        return jsonify({"has_access": False, "error": str(e)})

@app.route('/api/stats')
def global_stats():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) as count FROM users')
        total_users = c.fetchone()['count']
        c.execute('''SELECT COUNT(*) as active, AVG(best_streak) as avg_best, MAX(best_streak) as max_best, 
                     AVG(total_days) as avg_days, SUM(total_days) as total_all FROM user_progress''')
        stats = c.fetchone()
        conn.close()
        return jsonify({
            "status": "ok",
            "total_users": total_users,
            "active_users": stats['active'] or 0,
            "avg_best_streak": round(stats['avg_best'] or 0, 1),
            "max_streak": stats['max_best'] or 0,
            "avg_total_days": round(stats['avg_days'] or 0, 1),
            "total_days_all": stats['total_all'] or 0
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/platega/webhook', methods=['POST'])
def platega_webhook():
    """Принимает уведомления об оплате от Platega"""
    data = request.json
    invoice_id = data.get('invoice_id') or data.get('id')
    status = data.get('status')
    
    if status == 'paid':
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT user_id, plan FROM customers WHERE platega_invoice_id = ?', (invoice_id,))
        row = c.fetchone()
        
        if row:
            user_id, plan = row[0], row[1]
            if plan == 'premium':
                c.execute('''INSERT OR REPLACE INTO premium_users (user_id, activated_at, plan) 
                           VALUES (?, ?, 'premium')''', (user_id, datetime.now().isoformat()))
            elif plan == 'basic':
                c.execute('''INSERT OR REPLACE INTO basic_users (user_id, activated_at, plan) 
                           VALUES (?, ?, 'basic')''', (user_id, datetime.now().isoformat()))
            c.execute('UPDATE customers SET status = "activated" WHERE platega_invoice_id = ?', (invoice_id,))
            conn.commit()
        conn.close()
    
    return 'OK', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
