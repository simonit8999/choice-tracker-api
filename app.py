from flask import Flask, request, jsonify
import sqlite3
import json
from datetime import datetime
import os

app = Flask(__name__)

# Ручная обработка CORS
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

@app.route('/api/sync', methods=['OPTIONS'])
def handle_options():
    return '', 200

app = Flask(__name__)

# Конфигурация
API_SECRET = os.environ.get('API_SECRET', 'choice_super_secret_key_2025')
DB_PATH = os.environ.get('DB_PATH', '/tmp/choice_data.db')

def get_db():
    """Создаёт подключение к БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Инициализация базы данных"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  last_seen TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_progress
                 (user_id INTEGER PRIMARY KEY,
                  current_streak INTEGER DEFAULT 0,
                  best_streak INTEGER DEFAULT 0,
                  total_days INTEGER DEFAULT 0,
                  total_attempts INTEGER DEFAULT 0,
                  achievements TEXT DEFAULT '{}',
                  last_action TEXT,
                  last_update TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS attempts_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  start_date TEXT,
                  end_date TEXT,
                  days_completed INTEGER,
                  end_reason TEXT)''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

# Инициализируем БД при запуске
init_db()

@app.route('/')
def home():
    """Главная страница - проверка что API работает"""
    return jsonify({
        "status": "online",
        "app": "CHOICE Tracker API",
        "version": "1.0",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/sync', methods=['POST'])
def sync_data():
    """Синхронизация данных пользователя"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Сохраняем пользователя
        c.execute('''INSERT OR REPLACE INTO users 
                     (user_id, username, first_name, last_seen)
                     VALUES (?, ?, ?, ?)''',
                  (user_id, 
                   data.get('username', ''),
                   data.get('first_name', ''),
                   datetime.now().isoformat()))
        
        # Сохраняем прогресс
        progress = data.get('progress', {})
        achievements = data.get('achievements', {})
        
        c.execute('''INSERT OR REPLACE INTO user_progress
                     (user_id, current_streak, best_streak, total_days, 
                      total_attempts, achievements, last_update)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (user_id,
                   progress.get('current_streak', 0),
                   progress.get('best_streak', 0),
                   progress.get('total_days', 0),
                   progress.get('total_attempts', 0),
                   json.dumps(achievements),
                   datetime.now().isoformat()))
                # Сохраняем настройки уведомлений если есть
        notification = data.get('notification_settings')
        if notification:
            c.execute('''INSERT OR REPLACE INTO notification_settings
                         (user_id, enabled, reminder_hour, reminder_minute, timezone)
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id,
                       1 if notification.get('enabled') else 0,
                       int(notification.get('hour', 20)),
                       int(notification.get('minute', 0)),
                       notification.get('timezone', 'Europe/Moscow')))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "status": "ok", 
            "message": "Data synced successfully",
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error in sync_data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/load/<int:user_id>')
def load_data(user_id):
    """Загрузка данных пользователя"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Загружаем прогресс
        c.execute('''SELECT current_streak, best_streak, total_days, 
                     total_attempts, achievements 
                     FROM user_progress WHERE user_id = ?''', (user_id,))
        progress_row = c.fetchone()
        
        # Загружаем историю попыток
        c.execute('''SELECT start_date, end_date, days_completed, end_reason
                     FROM attempts_history 
                     WHERE user_id = ? 
                     ORDER BY id DESC LIMIT 10''', (user_id,))
        attempts = []
        for row in c.fetchall():
            attempts.append({
                'startDate': row['start_date'],
                'endDate': row['end_date'],
                'daysCompleted': row['days_completed'],
                'endReason': row['end_reason']
            })
        
        conn.close()
        
        if progress_row:
            return jsonify({
                "status": "ok",
                "data": {
                    "currentAttempt": {
                        "current_streak": progress_row['current_streak'],
                        "best_streak": progress_row['best_streak'],
                        "total_days": progress_row['total_days'],
                        "total_attempts": progress_row['total_attempts'],
                        "achievements": json.loads(progress_row['achievements'])
                    },
                    "attemptsHistory": attempts
                }
            })
        else:
            return jsonify({
                "status": "ok",
                "data": None,
                "message": "No data found for this user"
            })
            
    except Exception as e:
        print(f"Error in load_data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/action', methods=['POST'])
def log_action():
    """Логирование действия из Mini App"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        user_id = data.get('user_id')
        action = data.get('action')
        
        if not user_id or not action:
            return jsonify({"error": "user_id and action required"}), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Обновляем время последнего действия
        c.execute('''UPDATE user_progress 
                     SET last_action = ?, last_update = ?
                     WHERE user_id = ?''',
                  (action, datetime.now().isoformat(), user_id))
        
        # Логируем действие
        print(f"📝 User {user_id}: {action} at {datetime.now().isoformat()}")
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "status": "ok",
            "action": action,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error in log_action: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats')
def global_stats():
    """Глобальная статистика"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Количество пользователей
        c.execute('SELECT COUNT(*) as count FROM users')
        total_users = c.fetchone()['count']
        
        # Статистика прогресса
        c.execute('''SELECT 
                     COUNT(*) as active_users,
                     AVG(best_streak) as avg_best,
                     MAX(best_streak) as max_best,
                     AVG(total_days) as avg_days,
                     SUM(total_days) as total_days_all
                     FROM user_progress''')
        stats = c.fetchone()
        
        conn.close()
        
        return jsonify({
            "status": "ok",
            "total_users": total_users,
            "active_users": stats['active_users'] or 0,
            "avg_best_streak": round(stats['avg_best'] or 0, 1),
            "max_streak": stats['max_best'] or 0,
            "avg_total_days": round(stats['avg_days'] or 0, 1),
            "total_days_all": stats['total_days_all'] or 0
        })
        
    except Exception as e:
        print(f"Error in global_stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health_check():
    """Проверка здоровья сервера для UptimeRobot"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    # Для локального тестирования
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
