from flask import Flask, render_template, request, jsonify
import requests
import uuid
import time
import base64
import io
import struct
import random
import os
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes

app = Flask(__name__)

# --- CONFIGURATION ---
FB_APP_ID = "350685531728"
FB_APP_SECRET = "62f8ce9f74b12f84c123cc23437a4a32"
LITE_APP_ID = "275254692598279"
API_GRAPH = "https://b-graph.facebook.com"
API_METHOD = "https://api.facebook.com/method"

DEVICE_PROFILES = [
    {
        "model": "Pixel 8 Pro", "brand": "google", "os": "14", "build": "AP1A.240405.002",
        "width": 1344, "height": 2992, "density": 3.0, "fbav": "525.0.0.45.105", "fbbv": "650000000"
    },
    {
        "model": "SM-S918B", "brand": "samsung", "os": "13", "build": "TP1A.220624.014",
        "width": 1440, "height": 3088, "density": 3.0, "fbav": "525.0.0.45.105", "fbbv": "650000000"
    }
]

class DeviceFingerprint:
    def __init__(self):
        profile = random.choice(DEVICE_PROFILES)
        self.device_id = str(uuid.uuid4())
        self.family_device_id = str(uuid.uuid4())
        self.adid = str(uuid.uuid4())
        
        self.os_version = profile["os"]
        self.device_model = profile["model"]
        self.device_brand = profile["brand"]
        self.device_build = profile["build"]
        self.carrier = random.choice(["T-Mobile", "Verizon", "AT&T", "Jio"])
        self.locale = "en_US"
        self.fbav = profile["fbav"]
        self.fbbv = profile["fbbv"]
        self.arch = "arm64-v8a"
        self.density = profile["density"]
        self.width = profile["width"]
        self.height = profile["height"]
        
        self.user_agent = (
            f"Dalvik/2.1.0 (Linux; U; Android {self.os_version}; {self.device_model} Build/{self.device_build}) "
            f"[FBAN/FB4A;FBAV/{self.fbav};FBPN/com.facebook.katana;FBLC/{self.locale};FBBV/{self.fbbv};"
            f"FBCR/{self.carrier};FBMF/{self.device_brand};FBBD/{self.device_brand};FBDV/{self.device_model};"
            f"FBSV/{self.os_version};FBCA/{self.arch}:null;FBDM/density={self.density},width={self.width},height={self.height};"
            f"FB_FW/1;FBRV/0;]"
        )

    def get_headers(self):
        return {
            "User-Agent": self.user_agent,
            "X-FB-Connection-Quality": "EXCELLENT",
            "X-FB-Connection-Type": "WIFI",
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-FB-Friendly-Name": "authenticate",
            "X-FB-LDM": "1",
            "Accept-Language": self.locale.replace('_', '-')
        }

    def get_base_params(self):
        return {
            "device_id": self.device_id,
            "family_device_id": self.family_device_id,
            "adid": self.adid,
            "format": "json",
            "generate_analytics_claim": "1",
            "cpl": "true",
            "try_num": "1",
            "credentials_type": "password",
            "source": "login",
            "error_detail_type": "button_with_disabled",
            "enroll_misauth": "false",
            "generate_session_cookies": "1",
            "generate_machine_id": "1",
            "currently_logged_in_userid": "0",
            "fb_api_req_friendly_name": "authenticate",
            "fb_api_caller_class": "com.facebook.auth.login.AuthOperations"
        }

class FacebookPasswordEncryptor:
    @staticmethod
    def get_public_key():
        try:
            url = f'{API_GRAPH}/pwd_key_fetch'
            params = {
                'version': '2',
                'flow': 'CONTROLLER_INITIALIZATION',
                'method': 'GET',
                'fb_api_req_friendly_name': 'pwdKeyFetch',
                'fb_api_caller_class': 'com.facebook.auth.login.AuthOperations',
                'access_token': f'{FB_APP_ID}|{FB_APP_SECRET}'
            }
            response = requests.post(url, params=params).json()
            return response.get('public_key'), str(response.get('key_id', '25'))
        except Exception:
            return None, "25"

    @staticmethod
    def encrypt(password, public_key=None, key_id="25"):
        if public_key is None:
            public_key, key_id = FacebookPasswordEncryptor.get_public_key()
            if public_key is None: raise Exception("Key fetch failed")
            
        try:
            rand_key = get_random_bytes(32)
            iv = get_random_bytes(12)
            pubkey = RSA.import_key(public_key)
            cipher_rsa = PKCS1_v1_5.new(pubkey)
            encrypted_rand_key = cipher_rsa.encrypt(rand_key)
            cipher_aes = AES.new(rand_key, AES.MODE_GCM, nonce=iv)
            current_time = int(time.time())
            cipher_aes.update(str(current_time).encode("utf-8"))
            encrypted_passwd, auth_tag = cipher_aes.encrypt_and_digest(password.encode("utf-8"))
            buf = io.BytesIO()
            buf.write(bytes([1, int(key_id)]))
            buf.write(iv)
            buf.write(struct.pack("<h", len(encrypted_rand_key)))
            buf.write(encrypted_rand_key)
            buf.write(auth_tag)
            buf.write(encrypted_passwd)
            encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"#PWD_FB4A:2:{current_time}:{encoded}"
        except Exception as e:
            raise e

sessions_data = {}
recover_sessions = {}

def human_delay(min_s=0.3, max_s=0.8):
    time.sleep(random.uniform(min_s, max_s))

def internal_login(uid, raw_password, device, session):
    """Reusable function to get token after password is set"""
    try:
        pub_key, key_id = FacebookPasswordEncryptor.get_public_key()
        encrypted_password = FacebookPasswordEncryptor.encrypt(raw_password, pub_key, key_id)
        login_data = device.get_base_params()
        login_data.update({"email": uid, "password": encrypted_password})

        response = session.post(f"{API_GRAPH}/auth/login", data=login_data)
        res_data = response.json()
        
        if 'access_token' in res_data:
            return {'success': True, 'token': res_data['access_token']}
        
        if 'error' in res_data:
            err = res_data['error']
            return {'success': False, 'error': err.get('message', 'Login failed'), 'error_code': err.get('code')}
            
        return {'success': False, 'error': 'Unknown error'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/')
def index():
    return render_template('index.html')

# ==========================================
# 1. NORMAL LOGIN ROUTE
# ==========================================
@app.route('/login', methods=['POST'])
def login():
    uid = request.form.get('uid')
    password = request.form.get('password')
    if not uid or not password: return jsonify({'error': 'Required fields missing'})

    device = DeviceFingerprint()
    session = requests.Session()
    session.headers.update(device.get_headers())

    try:
        human_delay()
        pub_key, key_id = FacebookPasswordEncryptor.get_public_key()
        encrypted_password = FacebookPasswordEncryptor.encrypt(password, pub_key, key_id)
        login_data = device.get_base_params()
        login_data.update({"email": uid, "password": encrypted_password})

        human_delay()
        response = session.post(f"{API_GRAPH}/auth/login", data=login_data)
        res_data = response.json()
        
        if 'access_token' in res_data:
            return jsonify({'success': True, 'token': res_data['access_token']})

        if 'error' in res_data:
            err = res_data['error']
            err_data = err.get('error_data', {})
            is_2fa = err.get('code') in [317, 459] or 'login_first_factor' in err_data or 'approval' in err.get('message', '').lower()
            
            if is_2fa:
                session_id = str(uuid.uuid4())
                sessions_data[session_id] = {'uid': uid, 'err_data': err_data, 'device': device, 'session': session, 'login_data': login_data}
                return jsonify({'two_factor': True, 'session_id': session_id, 'device_approval': 'login_first_factor' in err_data})
            
            return jsonify({'success': False, 'error': err.get('message', 'Login failed')})
    except Exception as e:
        return jsonify({'error': str(e)})

# ==========================================
# 2. TWO FACTOR ROUTE (Approval / OTP)
# ==========================================
@app.route('/two_factor', methods=['POST'])
def two_factor():
    session_id = request.form.get('session_id')
    otp = request.form.get('otp', '').strip()
    if not session_id or session_id not in sessions_data: return jsonify({'error': 'Session expired'})
    
    s = sessions_data[session_id]
    login_data, err_data, device, session = s['login_data'], s['err_data'], s['device'], s['session']
    
    login_data['credentials_type'] = 'two_factor'
    if otp: login_data['twofactor_code'] = otp
    else: login_data.pop('twofactor_code', None)
        
    if 'uid' in err_data: login_data['userid'] = err_data['uid']
    if 'login_first_factor' in err_data:
        login_data['first_factor'] = err_data['login_first_factor']
        login_data['machine_id'] = err_data.get('machine_id', device.device_id)

    try:
        response = session.post(f"{API_GRAPH}/auth/login", data=login_data)
        res_data = response.json()
        
        if 'access_token' in res_data:
            del sessions_data[session_id]
            return jsonify({'success': True, 'token': res_data['access_token']})
            
        if 'error' in res_data:
            if not otp and res_data['error'].get('code') in [317, 459, 1348136]: 
                return jsonify({'success': False, 'waiting': True})
            del sessions_data[session_id]
            return jsonify({'success': False, 'error': res_data['error'].get('message', 'Failed')})
    except Exception as e:
        return jsonify({'error': str(e)})

# ==========================================
# 3. FORGOT PASSWORD (RECOVERY) ROUTES
# ==========================================
@app.route('/recover/send', methods=['POST'])
def recover_send():
    uid = request.form.get('uid')
    if not uid: return jsonify({'error': 'Email/Phone required'})
    
    device = DeviceFingerprint()
    session = requests.Session()
    session.headers.update(device.get_headers())
    
    data = device.get_base_params()
    data.update({'uid': uid, 'credentials_type': 'password', 'fb_api_req_friendly_name': 'recover'})
    
    try:
        res = session.post(f"{API_GRAPH}/auth/recover", data=data)
        res_data = res.json()
        
        if 'error' in res_data:
            return jsonify({'error': res_data['error'].get('message', 'Recovery failed')})
            
        # Session save karo next steps ke liye
        rec_id = str(uuid.uuid4())
        recover_sessions[rec_id] = {
            'uid': uid, 'device': device, 'session': session, 
            'data': data, 'recovery_code': res_data.get('recovery_code')
        }
        return jsonify({'success': True, 'recover_id': rec_id, 'message': 'OTP Sent successfully'})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/recover/verify', methods=['POST'])
def recover_verify():
    rec_id = request.form.get('recover_id')
    otp = request.form.get('otp')
    if not rec_id or rec_id not in recover_sessions: return jsonify({'error': 'Session expired'})
    
    s = recover_sessions[rec_id]
    s['data'].update({'recovery_code': otp, 'fb_api_req_friendly_name': 'recover_verify_code'})
    
    try:
        res = s['session'].post(f"{API_GRAPH}/auth/recover/verify_code", data=s['data'])
        res_data = res.json()
        
        if 'error' in res_data:
            return jsonify({'error': res_data['error'].get('message', 'Invalid OTP')})
        
        # Save recovery_token
        s['recovery_token'] = res_data.get('recovery_token')
        return jsonify({'success': True, 'message': 'OTP Verified'})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/recover/reset', methods=['POST'])
def recover_reset():
    rec_id = request.form.get('recover_id')
    new_password = request.form.get('password')
    if not rec_id or rec_id not in recover_sessions: return jsonify({'error': 'Session expired'})
    
    s = recover_sessions[rec_id]
    if not s.get('recovery_token'): return jsonify({'error': 'Verify OTP first'})
    
    try:
        # 1. Encrypt New Password
        pub_key, key_id = FacebookPasswordEncryptor.get_public_key()
        enc_pw = FacebookPasswordEncryptor.encrypt(new_password, pub_key, key_id)
        
        # 2. Change Password
        s['data'].update({
            'password': enc_pw,
            'recovery_token': s['recovery_token'],
            'fb_api_req_friendly_name': 'recover_change_password'
        })
        res = s['session'].post(f"{API_GRAPH}/auth/recover/change_password", data=s['data'])
        res_data = res.json()
        
        if 'error' in res_data:
            return jsonify({'error': res_data['error'].get('message', 'Password reset failed')})
            
        # 3. JUGAD: Turant naye password se login karo!
        del recover_sessions[rec_id]
        login_res = internal_login(s['uid'], new_password, s['device'], s['session'])
        
        if login_res.get('success'):
            return jsonify({'success': True, 'token': login_res['token'], 'message': 'Password reset & Logged in!'})
        else:
            return jsonify({'error': f"Password reset hua, par login fail: {login_res.get('error')}"})
            
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)