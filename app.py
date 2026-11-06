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

# Default UA for Graph API calls (FB4A style)
DEFAULT_UA = (
    "Dalvik/2.1.0 (Linux; U; Android 14; Pixel 8 Pro Build/AP1A.240405.002) "
    "[FBAN/FB4A;FBAV/460.0.0.42.109;FBPN/com.facebook.katana;FBLC/en_US;"
    "FBBV/585672584;FBCR/T-Mobile;FBMF/google;FBBD/google;FBDV/Pixel 8 Pro;"
    "FBSV/14;FBCA/arm64-v8a:null;FBDM/density=3.0,width=1344,height=2992;"
    "FB_FW/1;FBRV/0;]"
)


def get_mimetype(filename):
    """Determine the correct MIME type for a file."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or 'application/octet-stream'


def human_delay(min_s=0.3, max_s=0.8):
    """Simulates human-like network latency."""
    time.sleep(random.uniform(min_s, max_s))


def send_fb_message(token, thread_id, message_text=None, file_path=None, file_name=None, custom_ua=None):
    """
    Sends a message to a Facebook thread using a Personal Account Token (EAADV7).
    """
    if not token or not thread_id:
        return {"success": False, "error": "Token or Thread ID is missing"}

    # Personal Account Endpoint: POST /{thread_id}
    url = f"https://graph.facebook.com/v19.0/{thread_id}"
    
    ua = custom_ua if custom_ua else DEFAULT_UA

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": ua,
        "Content-Type": "application/json"
    }

    # Construct the message object
    # For personal accounts, the payload is the message content itself
    message_obj = {}

    # 1. Add Text if present
    if message_text:
        message_obj["message"] = message_text

    # 2. Add File Attachment if present
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
            
            file_b64 = base64.b64encode(file_bytes).decode('utf-8')
            mime_type = get_mimetype(file_name)
            
            # Attachment structure for Personal Account Tokens
            attachment = {
                "type": "file",
                "payload": {
                    "is_url": False,
                    "is_base64": True,
                    "base64": file_b64,
                    "filename": file_name,
                    "mime_type": mime_type
                }
            }
            
            # Initialize attachments list if not present
            if "attachments" not in message_obj:
                message_obj["attachments"] = []
            
            message_obj["attachments"].append(attachment)
        except Exception as e:
            return {"success": False, "error": f"Failed to read/process file: {str(e)}"}

    # 3. Fallback if no text and no file
    if not message_text and not (file_path and os.path.exists(file_path)):
        message_obj["message"] = "Hello from Automation Bot"

    # The final payload is just the message object
    payload = message_obj

    try:
        human_delay()
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        res_json = response.json()
        
        # Check for success
        # Personal account API returns the message object directly (e.g., {"id": "..."})
        if response.status_code == 200:
            return {
                "success": True,
                "message_id": res_json.get('id', 'N/A'),
                "thread_id": thread_id,
                "response": res_json
            }
        else:
            return {
                "success": False,
                "error": res_json.get('error', {}).get('message', 'Unknown API Error'),
                "code": res_json.get('error', {}).get('code', response.status_code),
                "response": res_json
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


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
        # Sanitize filename to prevent path traversal
        safe_name = os.path.basename(file_name)
        file_path = os.path.join(UPLOAD_FOLDER, safe_name)
        file.save(file_path)

    if not token or not thread_id:
        return jsonify({"success": False, "error": "Token and Thread ID are required"})

    result = send_fb_message(
        token, thread_id, message_text, file_path, file_name,
        custom_ua if custom_ua else None
    )

    # Cleanup file after sending
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    return jsonify(result)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)