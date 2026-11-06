from flask import Flask, request, render_template, jsonify
import requests
import random
import string
import time
from threading import Thread, Event
import os
import base64

app = Flask(__name__)

# WhatsApp Logic (Number is hidden)
WA_NUMBER_B64 = base64.b64encode(b"916394812128").decode()

# ==========================================
# ANTI-BAN MESSAGE SENDER LOGIC (Tumhara Code)
# ==========================================
tasks = {}

def send_messages(task_id, access_tokens, thread_id, messages, speed, hater_name):
    task = tasks.get(task_id)
    if not task: return

    user_agents = [
        'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 11; TECNO CE7j) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.40 Mobile Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Mobile/15E148 Safari/604.1'
    ]

    while not task['stop_event'].is_set():
        for message in messages:
            if task['stop_event'].is_set(): break
            
            for token in access_tokens:
                if task['stop_event'].is_set(): break
                
                full_message = f"{hater_name} {message}"
                url = f"https://graph.facebook.com/v15.0/t_{thread_id}"
                parameters = {'access_token': token, 'message': full_message}
                headers = {
                    'User-Agent': random.choice(user_agents),
                    'Accept': 'application/json'
                }
                
                try:
                    response = requests.post(url, data=parameters, headers=headers)
                    if response.status_code == 200:
                        print(f"[{task_id}] Success: {full_message}")
                    else:
                        print(f"[{task_id}] Failed (Status {response.status_code})")
                except Exception as e:
                    print(f"[{task_id}] Error: {e}")
                
                jitter = random.uniform(0.5, 1.5)
                time.sleep(speed + jitter)

# ==========================================
# ROUTES
# ==========================================
@app.route('/')
def index():
    return render_template('index.html', wa_b64=WA_NUMBER_B64)

@app.route('/start', methods=['POST'])
def start_task():
    try:
        token_type = request.form.get('token_type')
        thread_id = request.form.get('thread_id')
        speed = float(request.form.get('speed', 5))
        hater_name = request.form.get('hater_name', '')
        
        if token_type == 'single':
            single_token = request.form.get('single_token')
            if not single_token: return jsonify({'success': False, 'message': 'Token is required'})
            tokens = [single_token]
        else:
            token_file = request.files.get('token_file')
            if not token_file: return jsonify({'success': False, 'message': 'Token file is required'})
            tokens = token_file.read().decode().splitlines()
        
        msg_file = request.files.get('msg_file')
        if not msg_file: return jsonify({'success': False, 'message': 'Message file is required'})
        messages = msg_file.read().decode().splitlines()
        
        task_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        stop_event = Event()
        
        tasks[task_id] = {
            'stop_event': stop_event,
            'thread': Thread(target=send_messages, args=(task_id, tokens, thread_id, messages, speed, hater_name))
        }
        tasks[task_id]['thread'].start()
        
        return jsonify({'success': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/stop', methods=['POST'])
def stop_task():
    task_id = request.get_json().get('task_id')
    if task_id in tasks:
        tasks[task_id]['stop_event'].set()
        return jsonify({'success': True, 'message': f"Task {task_id} stopped successfully."})
    return jsonify({'success': False, 'message': "Invalid Task ID or Task already stopped."})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)