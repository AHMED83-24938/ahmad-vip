#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArenaScore - Telegram Bot & Encrypted M3U Backend Server
Hardened Security Architecture: Anti-Interception, Dynamic HMAC SHA256 Signatures, AES-256-CBC, Timestamp & Nonce Verification
"""

import os
import sys
import json
import time
import hmac
import base64
import hashlib
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import urllib.request
import urllib.parse

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
except ImportError:
    print("PyCryptodome required. Install via: pip install pycryptodome")
    # Native fallback if needed or exit

# Ultra-Secure 256-bit Cryptographic Secrets matching Android App's Obfuscated Key Engine
AES_SECRET_RAW = b"ArenaScore_UltraSecure_AESKey2026_!#987"
HMAC_SECRET_RAW = b"ArenaScore_UltraSecure_HMACKey2026_@$654"
IV_SECRET_RAW = b"ArenaScore_IV2026_!#"

AES_KEY = hashlib.sha256(AES_SECRET_RAW).digest()
HMAC_KEY = hashlib.sha256(HMAC_SECRET_RAW).digest()
AES_IV = hashlib.md5(IV_SECRET_RAW).digest()[:16]

# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
M3U_FILE = os.path.join(DATA_DIR, "playlist.m3u")
ENC_M3U_FILE = os.path.join(DATA_DIR, "playlist.enc")

os.makedirs(DATA_DIR, exist_ok=True)

# Helper Encryption & HMAC Signature Functions
def aes_encrypt(plain_bytes: bytes) -> bytes:
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return cipher.encrypt(pad(plain_bytes, AES.block_size))

def aes_decrypt(cipher_bytes: bytes) -> bytes:
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return unpad(cipher.decrypt(cipher_bytes), AES.block_size)

def encrypt_string(text: str) -> str:
    enc = aes_encrypt(text.encode("utf-8"))
    return base64.b64encode(enc).decode("utf-8")

def decrypt_string(b64_text: str) -> str:
    try:
        raw = base64.b64decode(b64_text)
        dec = aes_decrypt(raw)
        return dec.decode("utf-8")
    except Exception:
        return ""

def compute_hmac_signature(method: str, path: str, timestamp: str, nonce: str, payload: str) -> str:
    msg = f"{method.upper()}|{path}|{timestamp}|{nonce}|{payload}"
    return hmac.new(HMAC_KEY, msg.encode("utf-8"), hashlib.sha256).hexdigest()

def verify_request_signature(method: str, path: str, timestamp: str, nonce: str, payload: str, received_sig: str) -> bool:
    if not received_sig or not timestamp or not nonce:
        return False
    expected = compute_hmac_signature(method, path, timestamp, nonce, payload)
    return hmac.compare_digest(expected.lower(), received_sig.strip().lower())

# Replay Attack Prevention & Rate Limiting Engine
USED_NONCES = {} # nonce -> timestamp
IP_REQUESTS = {} # ip -> list of timestamps

def cleanup_nonces():
    now = time.time()
    expired = [n for n, ts in USED_NONCES.items() if now - ts > 120]
    for n in expired:
        del USED_NONCES[n]

def check_rate_limit(client_ip: str) -> bool:
    now = time.time()
    timestamps = IP_REQUESTS.get(client_ip, [])
    timestamps = [t for t in timestamps if now - t < 60]
    IP_REQUESTS[client_ip] = timestamps
    if len(timestamps) >= 30: # Maximum 30 requests per minute per IP
        return False
    timestamps.append(now)
    return True

# Default Config Setup
DEFAULT_CONFIG = {
    "bot_token": "8573246007:AAFbhcT7y9w938Gx2eJdU6GWdAnkN5Rr384",
    "activation_code": "AHMAD2026",
    "admins": [6803988521]  # Replace with primary admin Telegram User ID
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

def get_m3u_content():
    if os.path.exists(M3U_FILE):
        try:
            with open(M3U_FILE, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            pass
    return "#EXTM3U\n"

def set_m3u_content(content: str):
    with open(M3U_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    enc = aes_encrypt(content.encode("utf-8"))
    with open(ENC_M3U_FILE, "wb") as f:
        f.write(enc)

# Initial default M3U file setup from parent directory if present
DEFAULT_M3U_SOURCE = os.path.join(os.path.dirname(BASE_DIR), "app", "src", "main", "assets", "default_playlist.enc")
if not os.path.exists(M3U_FILE) and os.path.exists(DEFAULT_M3U_SOURCE):
    try:
        with open(DEFAULT_M3U_SOURCE, "rb") as f:
            enc_data = f.read()
        raw_m3u = aes_decrypt(enc_data).decode("utf-8")
        set_m3u_content(raw_m3u)
        print("Initialized default M3U playlist successfully.")
    except Exception as e:
        print("Failed to initialize default M3U:", e)

# -------------------------------------------------------------
# Hardened Encrypted & Signed HTTP API Server
# -------------------------------------------------------------
class EncryptedApiHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Suppress noisy HTTP logs
        pass

    def send_encrypted_response(self, status_code, data_dict):
        json_str = json.dumps(data_dict)
        enc_payload = encrypt_string(json_str)

        resp_ts = str(int(time.time() * 1000))
        resp_nonce = os.urandom(8).hex()
        resp_sig = compute_hmac_signature("RESPONSE", "/api/verify_code", resp_ts, resp_nonce, enc_payload)

        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Server", "ArenaScore-SecurityServer/1.1")
        self.send_header("X-Timestamp", resp_ts)
        self.send_header("X-Nonce", resp_nonce)
        self.send_header("X-Signature", resp_sig)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(enc_payload.encode("utf-8"))

    def send_access_denied(self):
        self.send_response(403)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Server", "ArenaScore-SecurityServer/1.1")
        self.end_headers()
        self.wfile.write(b"403 Forbidden")

    def do_GET(self):
        # Any browser or unauthorized GET request is strictly rejected
        self.send_access_denied()

    def do_POST(self):
        client_ip = self.client_address[0]
        if not check_rate_limit(client_ip):
            self.send_access_denied()
            return

        # Read POST body ONCE safely
        length = int(self.headers.get("Content-Length", 0))
        if length > 65536: # Exceeds max payload limit
            self.send_access_denied()
            return

        post_data = ""
        if length > 0:
            try:
                post_data = self.rfile.read(length).decode("utf-8", errors="ignore")
            except Exception:
                pass

        parsed = urlparse(self.path)
        if parsed.path == "/api/verify_code":
            ts = self.headers.get("X-Timestamp", "")
            nonce = self.headers.get("X-Nonce", "")
            received_sig = self.headers.get("X-Signature", "")

            # Timestamp Freshness Check (Max 60 Seconds skew allowed)
            try:
                req_time_ms = int(ts)
                curr_time_ms = int(time.time() * 1000)
                if abs(curr_time_ms - req_time_ms) > 60000:
                    self.send_access_denied()
                    return
            except Exception:
                self.send_access_denied()
                return

            # Replay Attack Prevention
            cleanup_nonces()
            if nonce in USED_NONCES:
                self.send_access_denied()
                return

            payload_str = ""
            if "payload=" in post_data:
                qs = parse_qs(post_data)
                payload_str = qs.get("payload", [""])[0]
            else:
                payload_str = post_data.strip()

            # Verify HMAC-SHA256 Signature over Request
            if not verify_request_signature("POST", "/api/verify_code", ts, nonce, payload_str, received_sig):
                self.send_access_denied()
                return

            # Record Nonce
            USED_NONCES[nonce] = time.time()

            # Decrypt Payload
            user_code = decrypt_string(payload_str)
            if not user_code:
                user_code = payload_str.strip()

            cfg = load_config()
            active_code = cfg.get("activation_code", "AHMAD2026")

            if user_code.strip() == active_code.strip():
                m3u_content = get_m3u_content()
                self.send_encrypted_response(200, {
                    "valid": True,
                    "message": "Activation successful",
                    "m3u": m3u_content
                })
            else:
                self.send_encrypted_response(200, {
                    "valid": False,
                    "message": "Invalid activation code"
                })
        else:
            self.send_access_denied()

def run_http_server(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, EncryptedApiHandler)
    print(f"🔒 Encrypted & Signed API Server running on port {port}...")
    httpd.serve_forever()

# -------------------------------------------------------------
# Telegram Bot Service
# -------------------------------------------------------------
class TelegramBotService:
    def __init__(self):
        self.cfg = load_config()
        self.bot_token = self.cfg.get("bot_token", "")
        self.offset = 0
        # Pending action for each admin: add/remove admin, add channel, or delete channel.
        self.pending = {}

    def api_call(self, method, data=None):
        if not self.bot_token or self.bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
            return None
        url = f"https://api.telegram.org/bot{self.bot_token}/{method}"
        try:
            if data:
                encoded = urllib.parse.urlencode(data).encode("utf-8")
                req = urllib.request.Request(url, data=encoded)
            else:
                req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            print(f"Telegram API Error ({method}): {e}")
            return None

    def send_message(self, chat_id, text, keyboard=True):
        data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if keyboard:
            data["reply_markup"] = json.dumps({
                "keyboard": [
                    [{"text": "➕ إضافة أدمن"}, {"text": "➖ مسح أدمن"}],
                    [{"text": "🔗 إضافة قناة برابط"}, {"text": "📁 إضافة قنوات من ملف"}],
                    [{"text": "🗑️ مسح قنوات"}, {"text": "📋 قائمة القنوات"}],
                    [{"text": "📊 الحالة"}, {"text": "❌ إلغاء"}]
                ],
                "resize_keyboard": True,
                "is_persistent": True
            }, ensure_ascii=False)
        return self.api_call("sendMessage", data)

    def channel_entries(self):
        """Return M3U channels as (name, url, raw_lines) entries."""
        lines = get_m3u_content().splitlines()
        entries = []
        current = None
        for line in lines:
            if line.startswith("#EXTINF:"):
                if current:
                    entries.append(current)
                name = line.rsplit(",", 1)[-1].strip() if "," in line else "قناة بدون اسم"
                current = {"name": name, "extinf": line, "url": ""}
            elif current and line.strip() and not line.startswith("#"):
                current["url"] = line.strip()
                entries.append(current)
                current = None
        if current:
            entries.append(current)
        return entries

    def add_channel_to_playlist(self, name, url):
        name = name.strip()
        url = url.strip()
        if not name or not url or not (url.startswith("http://") or url.startswith("https://")):
            return False, "أرسل اسم قناة ورابط بث يبدأ بـ http:// أو https://."
        content = get_m3u_content()
        if not content.startswith("#EXTM3U"):
            content = "#EXTM3U\\n"
        if not content.endswith("\\n"):
            content += "\\n"
        content += f'#EXTINF:-1,{name}\\n{url}\\n'
        set_m3u_content(content)
        return True, "تمت إضافة القناة وتحديث ملف القنوات."

    def download_file(self, file_id):
        res = self.api_call("getFile", {"file_id": file_id})
        if res and res.get("ok"):
            file_path = res["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            try:
                req = urllib.request.Request(download_url)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return resp.read().decode("utf-8", errors="ignore")
            except Exception as e:
                print("Download Error:", e)
        return None

    def is_admin(self, user_id):
        self.cfg = load_config()
        admins = self.cfg.get("admins", [])
        return user_id in admins

    def handle_message(self, message):
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]
        text = message.get("text", "").strip()

        if not self.is_admin(user_id):
            self.send_message(chat_id, f"⛔ غير مصرح لك باستعمال هذا البوت.\nالآيدي الخاص بك: `{user_id}`\nراسل الأدمن لإضافتك.", keyboard=False)
            return

        # Main menu buttons and command aliases
        if text.startswith("/start") or text.startswith("/help"):
            self.pending.pop(user_id, None)
            self.send_message(chat_id,
                "⭐️ *لوحة تحكم القنوات*\n\nاختَر العملية من الأزرار:\n"
                "➕ إضافة أدمن أو ➖ مسح أدمن\n"
                "🔗 إضافة قناة برابط بث\n"
                "📁 رفع ملف M3U/TXT لإضافة أو استبدال قائمة القنوات\n"
                "🗑️ مسح قناة حسب الرقم من القائمة.")
            return

        if text == "❌ إلغاء" or text.startswith("/cancel"):
            self.pending.pop(user_id, None)
            self.send_message(chat_id, "تم إلغاء العملية.")
            return

        if text == "➕ إضافة أدمن" or text.startswith("/addadmin"):
            parts = text.split()
            if text.startswith("/addadmin") and len(parts) > 1 and parts[1].isdigit():
                new_id = int(parts[1])
                self.cfg = load_config()
                admins = self.cfg.setdefault("admins", [])
                if new_id not in admins:
                    admins.append(new_id)
                    save_config(self.cfg)
                    self.send_message(chat_id, f"✅ تمت إضافة الأدمن.\nID: `{new_id}`")
                else:
                    self.send_message(chat_id, "هذا المستخدم أدمن بالفعل.")
            else:
                self.pending[user_id] = {"action": "add_admin"}
                self.send_message(chat_id, "أرسل آيدي تيليجرام للشخص الذي تريد إضافته كأدمن.")
            return

        if text == "➖ مسح أدمن" or text.startswith("/removeadmin"):
            parts = text.split()
            if text.startswith("/removeadmin") and len(parts) > 1 and parts[1].isdigit():
                target = int(parts[1])
                self.remove_admin(chat_id, target)
            else:
                self.pending[user_id] = {"action": "remove_admin"}
                self.send_message(chat_id, "أرسل آيدي الأدمن الذي تريد حذفه.")
            return

        if text == "🔗 إضافة قناة برابط" or text.startswith("/addchannel"):
            parts = text.split(maxsplit=1)
            if text.startswith("/addchannel") and len(parts) > 1 and "|" in parts[1]:
                name, url = parts[1].split("|", 1)
                ok, result = self.add_channel_to_playlist(name, url)
                self.send_message(chat_id, ("✅ " if ok else "⚠️ ") + result)
            else:
                self.pending[user_id] = {"action": "add_channel_name"}
                self.send_message(chat_id, "أرسل اسم القناة أولاً.")
            return

        if text == "📁 إضافة قنوات من ملف":
            self.pending.pop(user_id, None)
            self.send_message(chat_id, "أرسل ملف القنوات بصيغة `.m3u` أو `.m3u8` أو `.txt` كمستند. سيتم استبدال القائمة الحالية بمحتوى الملف.")
            return

        if text == "🗑️ مسح قنوات" or text.startswith("/deletechannel"):
            entries = self.channel_entries()
            if not entries:
                self.send_message(chat_id, "لا توجد قنوات في القائمة لمسحها.")
                return
            lines = ["🗑️ *قائمة القنوات — أرسل رقم القناة لمسحها:*"]
            for i, item in enumerate(entries[:100], 1):
                lines.append(f"`{i}` — {item['name']}")
            if len(entries) > 100:
                lines.append(f"... توجد {len(entries)} قناة. اعرض أول 100 فقط.")
            self.pending[user_id] = {"action": "delete_channel"}
            self.send_message(chat_id, "\n".join(lines))
            return

        if text == "📋 قائمة القنوات":
            entries = self.channel_entries()
            if not entries:
                self.send_message(chat_id, "قائمة القنوات فارغة.")
            else:
                lines = [f"📺 *عدد القنوات: {len(entries)}*"]
                lines.extend(f"`{i}` — {item['name']}" for i, item in enumerate(entries[:100], 1))
                self.send_message(chat_id, "\n".join(lines))
            return

        if text == "📊 الحالة" or text.startswith("/status"):
            self.cfg = load_config()
            entries = self.channel_entries()
            self.send_message(chat_id,
                f"📊 *الحالة*\n\n📺 عدد القنوات: `{len(entries)}`\n"
                f"👥 عدد الأدمنية: `{len(self.cfg.get('admins', []))}`\n"
                f"🔐 كود التفعيل: `{self.cfg.get('activation_code', 'غير محدد')}`")
            return

        # Continue any pending multi-step operation
        pending = self.pending.get(user_id)
        if pending:
            action = pending.get("action")

            if action in ("add_admin", "remove_admin"):
                if not text.isdigit():
                    self.send_message(chat_id, "آيدي غير صحيح. أرسل أرقام الآيدي فقط، أو اضغط ❌ إلغاء.")
                    return
                target = int(text)
                self.pending.pop(user_id, None)
                if action == "add_admin":
                    self.cfg = load_config()
                    admins = self.cfg.setdefault("admins", [])
                    if target in admins:
                        self.send_message(chat_id, "هذا المستخدم أدمن بالفعل.")
                    else:
                        admins.append(target)
                        save_config(self.cfg)
                        self.send_message(chat_id, f"✅ تمت إضافة الأدمن بنجاح.\nID: `{target}`")
                else:
                    self.remove_admin(chat_id, target)
                return

            if action == "add_channel_name":
                if not text or text.startswith("/"):
                    self.send_message(chat_id, "أرسل اسم قناة صحيحاً.")
                    return
                self.pending[user_id] = {"action": "add_channel_url", "name": text}
                self.send_message(chat_id, "هسه أرسل رابط البث المباشر للقناة (HTTP أو HTTPS).")
                return

            if action == "add_channel_url":
                name = pending.get("name", "")
                self.pending.pop(user_id, None)
                ok, result = self.add_channel_to_playlist(name, text)
                self.send_message(chat_id, ("✅ " if ok else "⚠️ ") + result)
                return

            if action == "delete_channel":
                if not text.isdigit():
                    self.send_message(chat_id, "أرسل رقم القناة فقط، أو اضغط ❌ إلغاء.")
                    return
                index = int(text)
                entries = self.channel_entries()
                if index < 1 or index > len(entries):
                    self.send_message(chat_id, f"الرقم غير صحيح. اختر رقماً بين 1 و {len(entries)}.")
                    return
                target = entries[index - 1]
                lines = get_m3u_content().splitlines()
                output = []
                i = 0
                channel_index = 0
                while i < len(lines):
                    if lines[i].startswith("#EXTINF:"):
                        channel_index += 1
                        if channel_index == index:
                            i += 1
                            # Skip channel metadata/comments until the stream URL, then skip URL too.
                            while i < len(lines) and (not lines[i].strip() or lines[i].startswith("#")):
                                i += 1
                            if i < len(lines):
                                i += 1
                            continue
                    output.append(lines[i])
                    i += 1
                content = "\n".join(output).strip() + "\n"
                if not content.startswith("#EXTM3U"):
                    content = "#EXTM3U\n" + content
                set_m3u_content(content)
                self.pending.pop(user_id, None)
                self.send_message(chat_id, f"🗑️ تم مسح القناة: *{target['name']}*")
                return

        # Accept channel file uploads
        if "document" in message:
            doc = message["document"]
            file_name = doc.get("file_name", "").lower()
            file_id = doc.get("file_id")
            if file_name.endswith((".m3u", ".m3u8", ".txt")):
                self.send_message(chat_id, "⏳ جاري تحميل ملف القنوات...")
                content = self.download_file(file_id)
                if content and "#EXT" in content:
                    if not content.startswith("#EXTM3U"):
                        content = "#EXTM3U\n" + content
                    set_m3u_content(content)
                    count = content.count("#EXTINF:")
                    self.send_message(chat_id, f"✅ تم تحديث ملف القنوات بنجاح.\nعدد القنوات: `{count}`")
                else:
                    self.send_message(chat_id, "❌ الملف غير صالح أو لا يحتوي على قنوات M3U.")
            else:
                self.send_message(chat_id, "أرسل ملف بصيغة `.m3u` أو `.m3u8` أو `.txt`.")
            return

        # Existing command compatibility
        if text.startswith("/setcode"):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                self.cfg = load_config()
                self.cfg["activation_code"] = parts[1].strip()
                save_config(self.cfg)
                self.send_message(chat_id, "✅ تم تغيير كود التفعيل.")
            else:
                self.send_message(chat_id, "الاستخدام: `/setcode الكود_الجديد`")
            return

        if text.startswith("/listadmins"):
            self.cfg = load_config()
            admins = self.cfg.get("admins", [])
            self.send_message(chat_id, "👥 *قائمة الأدمنية:*\n" + ("\n".join(f"`{a}`" for a in admins) if admins else "لا يوجد أدمنية."))
            return

        self.send_message(chat_id, "اختَر عملية من الأزرار، أو اكتب /start لعرض لوحة التحكم.")

    def remove_admin(self, chat_id, target):
        self.cfg = load_config()
        admins = self.cfg.setdefault("admins", [])
        # Protect the first configured admin from accidental removal.
        if admins and target == admins[0]:
            self.send_message(chat_id, "⛔ لا يمكن حذف الأدمن الأساسي.")
            return
        if target not in admins:
            self.send_message(chat_id, "هذا الآيدي غير موجود ضمن الأدمنية.")
            return
        admins.remove(target)
        save_config(self.cfg)
        self.send_message(chat_id, f"✅ تم حذف الأدمن.\nID: `{target}`")

    def start_polling(self):
        print("🤖 Telegram Bot Polling started...")
        while True:
            try:
                updates = self.api_call("getUpdates", {"offset": self.offset, "timeout": 20})
                if updates and updates.get("ok"):
                    for update in updates.get("result", []):
                        self.offset = update["update_id"] + 1
                        if "message" in update:
                            self.handle_message(update["message"])
            except Exception as e:
                print("Polling exception:", e)
            time.sleep(2)

if __name__ == "__main__":
    # Start HTTP API Server thread
    api_thread = threading.Thread(target=run_http_server, kwargs={"port": 8080}, daemon=True)
    api_thread.start()

    # Start Telegram Bot Service
    bot = TelegramBotService()
    bot.start_polling()
