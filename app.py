from flask import Flask, render_template, request, jsonify
import os
import time
import random
import requests
import base64
import mimetypes

app = Flask(__name__)

# --- CONFIGURATION ---
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- BRAND INFO ---
BRAND_NAME = "Eriic + Anurag Mishra"
# Number hidden publicly — encoded and decoded on client side
WA_NUMBER_B64 = base64.b64encode(b"916394812128").decode()

DEFAULT_UA = (
    "Dalvik/2.1.0 (Linux; U; Android 14; Pixel 8 Pro Build/AP1A.240405.002) "
    "[FBAN/FB4A;FBAV/460.0.0.42.109;FBPN/com.facebook.katana;FBLC/en_US;"
    "FBBV/585672584;FBCR/T-Mobile;FBMF/google;FBBD/google;FBDV/Pixel 8 Pro;"
    "FBSV/14;FBCA/arm64-v8a:null;FBDM/density=3.0,width=1344,height=2992;"
    "FB_FW/1;FBRV/0;]"
)


def get_mimetype(filename):
    mime, _ = mimetypes.guess_type(filename)
    return mime or 'application/octet-stream'


def human_delay(min_s=0.3, max_s=0.8):
    time.sleep(random.uniform(min_s, max_s))


def send_fb_message(token, thread_id, message_text=None, file_path=None, file_name=None, custom_ua=None):
    if not token or not thread_id:
        return {"success": False, "error": "Token or Thread ID is missing"}

    url = f"https://graph.facebook.com/v19.0/{thread_id}/messages"
    ua = custom_ua if custom_ua else DEFAULT_UA

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": ua,
        "Content-Type": "application/json"
    }

    if file_path and os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
        file_b64 = base64.b64encode(file_bytes).decode('utf-8')
        mime_type = get_mimetype(file_name)
        payload = {
            "recipient": {"id": thread_id},
            "messaging_type": "RESPONSE",
            "message": {
                "messaging_type": "RESPONSE",
                "attachments": [{
                    "type": "file",
                    "payload": {
                        "is_url": False,
                        "is_base64": True,
                        "base64": file_b64,
                        "filename": file_name,
                        "mime_type": mime_type
                    }
                }]
            }
        }
        if message_text:
            payload["message"]["text"] = message_text
    else:
        payload = {
            "recipient": {"id": thread_id},
            "messaging_type": "RESPONSE",
            "message": {
                "messaging_type": "RESPONSE",
                "text": message_text or "Hello from Automation Bot"
            }
        }

    try:
        human_delay()
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        res_json = response.json()
        if response.status_code == 200 and 'messages' in res_json:
            return {
                "success": True,
                "message_id": res_json['messages'][0]['id'],
                "thread_id": thread_id
            }
        else:
            return {
                "success": False,
                "error": res_json.get('error', {}).get('message', 'Unknown API Error'),
                "code": res_json.get('error', {}).get('code', response.status_code),
                "response": res_json
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- ROUTES ---
@app.route('/')
def index():
    return render_template(
        'index.html',
        brand_name=BRAND_NAME,
        wa_b64=WA_NUMBER_B64
    )


@app.route('/health')
def health():
    return jsonify({"status": "ok", "brand": BRAND_NAME})


@app.route('/send', methods=['POST'])
def send_message():
    token = request.form.get('token')
    thread_id = request.form.get('thread_id')
    message_text = request.form.get('message', '').strip()
    custom_ua = request.form.get('custom_ua', '').strip()

    file = request.files.get('file')
    file_path = None
    file_name = None

    if file and file.filename:
        file_name = file.filename
        safe_name = os.path.basename(file_name)
        file_path = os.path.join(UPLOAD_FOLDER, safe_name)
        file.save(file_path)

    if not token or not thread_id:
        return jsonify({"success": False, "error": "Token and Thread ID are required"})

    result = send_fb_message(
        token, thread_id, message_text, file_path, file_name,
        custom_ua if custom_ua else None
    )

    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    return jsonify(result)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
