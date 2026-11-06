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
WA_NUMBER_B64 = base64.b64encode(b"916394812128").decode()

# Default UA for Graph API calls (FB4A style)
DEFAULT_UA = (
    "Dalvik/2.1.0 (Linux; U; Android 14; Pixel 8 Pro Build/AP1A.240405.002) "
    "[FBAN/FB4A;FBAV/460.0.0.42.109;FBPN/com.facebook.katana;FBLC/en_US;"
    "FBBV/585672584;FBCR/T-Mobile;FBMF/google;FBBD/google;FBDV/Pixel 8 Pro;"
    "FBSV/14;FBCA/arm64-v8a:null;FBDM/density=3.0,width=1344,height=2992;"
    "FB_FW/1;FBRV/0;]"
)

# API Versions to try (Fallback mechanism)
API_VERSIONS = ["v20.0", "v19.0", "v18.0"]


def get_mimetype(filename):
    """Determine the correct MIME type for a file."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or 'application/octet-stream'


def human_delay(min_s=0.3, max_s=0.8):
    """Simulates human-like network latency."""
    time.sleep(random.uniform(min_s, max_s))


def build_payload(message_text, file_path, file_name):
    """
    Builds the payload for personal account tokens.
    """
    message_obj = {}

    if message_text:
        message_obj["message"] = message_text

    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
            file_b64 = base64.b64encode(file_bytes).decode('utf-8')
            mime_type = get_mimetype(file_name)
            
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
            if "attachments" not in message_obj:
                message_obj["attachments"] = []
            message_obj["attachments"].append(attachment)
        except Exception as e:
            return None, f"Failed to process file: {str(e)}"

    if not message_text and not (file_path and os.path.exists(file_path)):
        message_obj["message"] = "Hello from Automation Bot"

    return message_obj, None


def send_fb_message(token, thread_id, message_text=None, file_path=None, file_name=None, custom_ua=None):
    """
    Sends a message using a Personal Account Token (EAADV7).
    Tries multiple API versions to ensure compatibility.
    """
    if not token or not thread_id:
        return {"success": False, "error": "Token or Thread ID is missing"}

    payload, err = build_payload(message_text, file_path, file_name)
    if err:
        return {"success": False, "error": err}

    ua = custom_ua if custom_ua else DEFAULT_UA
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": ua,
        "Content-Type": "application/json"
    }

    last_error = None

    # Try different API versions
    for version in API_VERSIONS:
        url = f"https://graph.facebook.com/{version}/{thread_id}"
        
        try:
            human_delay()
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            res_json = response.json()
            
            # Success Check
            if response.status_code == 200:
                return {
                    "success": True,
                    "message_id": res_json.get('id', 'N/A'),
                    "thread_id": thread_id,
                    "api_version": version,
                    "response": res_json
                }
            
            # Capture error for fallback
            error_msg = res_json.get('error', {}).get('message', 'Unknown Error')
            error_code = res_json.get('error', {}).get('code', response.status_code)
            last_error = {"code": error_code, "message": error_msg, "version": version}
            
            # If error is 100 (Object does not exist), trying other versions might not help 
            # unless the ID is actually a Page ID or the token lacks permissions.
            # But we continue to try in case it's a version-specific quirk.
            if error_code != 100:
                continue
            else:
                # If Code 100, it's likely a token/ID mismatch. 
                # Breaking early if it's clearly a permission issue.
                if 'permissions' in error_msg.lower() or 'does not exist' in error_msg.lower():
                    # It might still work on an older version if the object structure changed, 
                    # but usually 100 is definitive. Let's try the next one just in case.
                    pass

        except Exception as e:
            last_error = {"code": "EXCEPTION", "message": str(e), "version": version}

    return {
        "success": False,
        "error": "All API versions failed",
        "last_error": last_error
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