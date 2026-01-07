import os
import json
import datetime
import tempfile
import random
import time
import base64
from functools import wraps
from bson import ObjectId
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from dotenv import load_dotenv
import csv
import io
import urllib.parse

# [UPDATED] Google GenAI (New SDK)
from google import genai
from google.genai import types

# Database & Image
from pymongo import MongoClient
import cloudinary
import cloudinary.uploader
from cloudinary.api import delete_resources_by_tag

# LINE SDK V3
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, MessagingApiBlob,
    ReplyMessageRequest, PushMessageRequest, TextMessage, ImageMessage
)
from linebot.v3.webhooks import (
    MessageEvent, 
    TextMessageContent, 
    ImageMessageContent, 
    FollowEvent
)

# ================= CONFIGURATION =================
load_dotenv()

app = Flask(__name__)

from werkzeug.middleware.proxy_fix import ProxyFix

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# เพิ่ม CORS configuration สำหรับ frontend
# เพิ่ม CORS configuration แบบกว้างเพื่อแก้ปัญหา Loading จม
CORS(app, origins="*", allow_headers="*")
app.config['CORS_HEADERS'] = 'Content-Type'

MONGO_URI = os.getenv("MONGO_URI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
CLOUDINARY_UPLOAD_PRESET = os.getenv("CLOUDINARY_UPLOAD_PRESET", "smart_condo")

API_TOKEN = os.getenv("API_TOKEN")



# ================= IMAGE VALIDATION =================
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'heic', 'heif'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_image(file):
    """
    ตรวจสอบนามสกุลไฟล์ และขนาดไฟล์
    """
    if not file:
        return False, "ไม่มีไฟล์"
    
    if not allowed_file(file.filename):
        return False, f"นามสกุลไฟล์ไม่รองรับ (รองรับ: {', '.join(ALLOWED_EXTENSIONS)})"
    
    # ตรวจสอบขนาดไฟล์
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)  # Reset pointer
    
    if size > MAX_FILE_SIZE:
        return False, f"ไฟล์มีขนาดใหญ่เกินไป (สูงสุด {MAX_FILE_SIZE // (1024*1024)}MB)"
        
    return True, "OK"

# ================= SETUP SERVICES =================
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["smart_condo"]
    users_col = db["users"]
    parcels_col = db["parcels"]
    complaints_col = db["complaints"]
    kb_col = db["knowledge_base"]
    admins_col = db["admins"]
    audit_logs_col = db["audit_logs"]  # เพิ่ม collection สำหรับ audit logs
    chat_history_col = db["chat_history"]  # เพิ่ม collection สำหรับบันทึกประวัติแชททั้งหมด
    
    print("✅ MongoDB Connected: smart_condo")
    # ตรวจสอบจำนวนข้อมูลเบื้องต้น
    print(f"📊 Database Stats:")
    print(f"   - Users: {users_col.count_documents({})}")
    print(f"   - Parcels: {parcels_col.count_documents({})}")
    print(f"   - Complaints: {complaints_col.count_documents({})}")
    print(f"   - Admins: {admins_col.count_documents({})}")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")

# [UPDATED] Setup Gemini Client (New SDK)
client = genai.Client(api_key=GEMINI_API_KEY)

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
)

line_configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
line_handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.before_request
def log_request_info():
    if request.path.startswith('/api'):
        print(f"🔍 Incoming Request: {request.method} {request.path}")

def get_bkk_now():
    """Get current usage time in Bangkok timezone (UTC+7)"""
    tz = datetime.timezone(datetime.timedelta(hours=7))
    return datetime.datetime.now(tz)

def analyze_urgency_from_description(text):
    """
    วิเคราะห์ความเร่งด่วนเบื้องต้นจากคำสำคัญในข้อความ (Rule-based)
    """
    if not text: return "Medium"
    text = text.lower()
    
    high_keywords = ['ไฟไหม้', 'ควัน', 'ประกายไฟ', 'ไฟช็อต', 'ไฟดูด', 'แก๊สรั่ว', 'กลิ่นแก๊ส', 'ระเบิด', 'น้ำท่วม', 'ท่อแตก', 'คนติด', 'ลิฟต์ค้าง', 'ประตูเสีย', 'ล็อคไม่ได้', 'อันตราย']
    medium_keywords = ['แอร์เสีย', 'แอร์ไม่เย็น', 'น้ำไม่ไหล', 'น้ำรั่ว', 'ส้วมตัน', 'กดไม่ลง', 'ไฟดับ', 'ไฟตก', 'อินเทอร์เน็ต', 'internet', 'wifi', 'ลิฟต์เสีย', 'มีกลิ่น', 'เสียงดัง']
    
    for kw in high_keywords:
        if kw in text: return "High"
        
    for kw in medium_keywords:
        if kw in text: return "Medium"
        
    return "Low"

def determine_final_urgency(desc_urgency, ai_urgency, text):
    """
    ตัดสินใจความเร่งด่วนขั้นสุดท้าย
    - ถ้า Keyword บอก High -> ให้ High ทันที (Safety First)
    - ถ้า Keyword Low แต่ AI บอก High -> เชื่อ AI (เผื่อมีภาพประกอบที่น่ากลัว)
    """
    # 1. Safety First: ถ้าเจอคำว่าไฟไหม้/แก๊สรั่ว ให้ High เสมอ
    if desc_urgency == "High":
        return "High"
        
    # 2. ถ้า AI เห็นว่า High (เช่น เห็นภาพไฟไหม้) -> High
    if ai_urgency == "High":
        return "High"
        
    # 3. ถ้า AI บอก Medium แต่ข้อความเป็น Low -> Medium (กันเหนียว)
    if ai_urgency == "Medium":
        return "Medium"
        
    return desc_urgency

def log_admin_action(action, performed_by, target=None, details=None):
    """
    บันทึกการดำเนินการของผู้ดูแลระบบ
    Args:
        action: การกระทำ (เช่น "Delete User", "Confirm Parcel", "Resolve Complaint")
        performed_by: ชื่อหรืออีเมลผู้ดำเนินการ
        target: เป้าหมาย (เช่น ห้อง, ID)
        details: รายละเอียดเพิ่มเติม
    """
    try:
        log_entry = {
            "action": action,
            "performed_by": performed_by,
            "target": target,
            "timestamp": datetime.datetime.utcnow(),
            "details": details or ""
        }
        audit_logs_col.insert_one(log_entry)
        print(f"📝 Audit Log: {action} by {performed_by} -> {target}")
        return True
    except Exception as e:
        print(f"❌ Audit Log Error: {e}")
        return False

# ================= CHAT HISTORY HELPER =================

def save_full_chat_history(line_user_id, role, message, platform="line"):
    """
    บันทึกประวัติแชททั้งหมดใน collection แยก
    Args:
        line_user_id: LINE User ID
        role: 'user' หรือ 'assistant' ('model')
        message: ข้อความ
        platform: 'line' หรือ 'web'
    """
    try:
        # ตรวจสอบและแปลง role
        if role == 'assistant' or role == 'model':
            role = 'assistant'
        
        chat_entry = {
            "line_user_id": line_user_id,
            "role": role,
            "message": message,
            "platform": platform,
            "timestamp": datetime.datetime.utcnow()
        }
        
        chat_history_col.insert_one(chat_entry)
        print(f"💾 Saved chat history: {role} message for {line_user_id}")
        return True
    except Exception as e:
        print(f"❌ Chat History Save Error: {e}")
        return False

# ================= SECURITY HELPER =================

def require_api_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # ตรวจสอบ Token จาก Header (X-API-Token) หรือ Query Parameter (token)
        request_token = request.headers.get('X-API-Token') or request.args.get('token')
        if not request_token or request_token != API_TOKEN:
            return jsonify({"status": "error", "message": "Unauthorized: Invalid or missing token"}), 401
        return f(*args, **kwargs)
    return decorated_function

# ================= ADMIN AUTH ENDPOINTS =================

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    """ตรวจสอบการล็อกอินของผู้ดูแลระบบ"""
    try:
        data = request.json
        
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400
        
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        
        if not email or not password:
            return jsonify({"status": "error", "message": "กรุณากรอกอีเมลและรหัสผ่าน"}), 400
        
        # ค้นหา admin จากฐานข้อมูล
        admin = admins_col.find_one({"email": email})
        
        if not admin:
            return jsonify({"status": "error", "message": "อีเมลหรือรหัสผ่านไม่ถูกต้อง"}), 401
        
        # ตรวจสอบรหัสผ่าน (ในตัวอย่างนี้เก็บเป็น plain text)
        # NOTE: ใน production ควรใช้ hashed password
        if admin.get('password') != password:
            return jsonify({"status": "error", "message": "อีเมลหรือรหัสผ่านไม่ถูกต้อง"}), 401
        
        # บันทึก audit log
        log_admin_action(
            action="Admin Login",
            performed_by=admin.get('name', email),
            target="System",
            details=f"Admin logged in from IP: {request.remote_addr}"
        )
        
        return jsonify({
            "status": "success",
            "message": "ล็อกอินสำเร็จ",
            "admin": {
                "name": admin.get('name'),
                "email": admin.get('email')
            }
        })
        
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({"status": "error", "message": "เกิดข้อผิดพลาดในการล็อกอิน"}), 500

@app.route('/api/admin/logout', methods=['POST'])
@require_api_token
def admin_logout():
    """บันทึกการออกจากระบบของผู้ดูแลระบบ"""
    try:
        # ✅ Decode ชื่อแอดมินจาก Header
        admin_name_header = request.headers.get('X-Admin-Name', 'Unknown Admin')
        admin_name = urllib.parse.unquote(admin_name_header)
        
        log_admin_action(
            action="Admin Logout",
            performed_by=admin_name,
            target="System",
            details=f"Admin logged out"
        )
        return jsonify({"status": "success", "message": "Logged out successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= LINE MESSAGE HELPER =================

def send_line_message(user_id, message, image_url=None):
    """ส่งข้อความ LINE ไปยังผู้ใช้ (แก้ไขให้รองรับการส่งรูปภาพ)"""
    try:
        with ApiClient(line_configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            messages = []
            
            # ส่งข้อความก่อน
            messages.append(TextMessage(text=message))
            
            # ส่งรูปภาพถ้ามีและ URL ถูกต้อง
            if image_url and image_url.strip() and image_url != "":
                try:
                    # ตรวจสอบว่า URL ใช้งานได้
                    import requests
                    response = requests.head(image_url, timeout=5)
                    
                    if response.status_code == 200:
                        messages.append(ImageMessage(
                            original_content_url=image_url, 
                            preview_image_url=image_url
                        ))
                        print(f"📷 Added image to message: {image_url}")
                    else:
                        print(f"⚠️ Image URL not accessible: {image_url} (Status: {response.status_code})")
                except Exception as img_error:
                    print(f"⚠️ Image URL check error: {img_error}")
            
            try:
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=messages
                    )
                )
                print(f"✅ Message sent to {user_id}")
                return True
            except Exception as api_error:
                print(f"❌ LINE API Error: {api_error}")
                
                # ลองส่งเฉพาะข้อความอย่างเดียว
                try:
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=user_id,
                            messages=[TextMessage(text=message)]
                        )
                    )
                    print(f"✅ Text-only message sent to {user_id}")
                    return True
                except Exception as text_error:
                    print(f"❌ Text-only also failed: {text_error}")
                    return False
                
    except Exception as e:
        print(f"❌ LINE Send Error: {e}")
        return False

# ================= USER SEARCH HELPER (ENHANCED) =================

def find_user_by_room_or_name(room_number=None, recipient_name=None):
    """ค้นหาผู้ใช้จากเลขห้องหรือชื่อผู้รับ (แก้ไขให้แม่นยำขึ้น)"""
    query = {}
    
    if room_number and room_number != "-":
        # Normalize room number: ลบช่องว่าง, ลบคำว่า "ห้อง"
        normalized_room = str(room_number).strip().replace("ห้อง", "").strip()
        # ลองค้นหาในหลายรูปแบบ
        query["$or"] = [
            {"room_number": normalized_room},
            {"room_number": f"ห้อง {normalized_room}"},
            {"room_number": f"Room {normalized_room}"},
            {"room_number": f"ROOM {normalized_room}"},
            {"room_number": {"$regex": f"^{normalized_room}$", "$options": "i"}}
        ]
    
    if recipient_name and recipient_name != "-":
        # ตรวจสอบชื่อในหลายรูปแบบ
        name_query = {
            "$or": [
                {"display_name": {"$regex": f".*{recipient_name}.*", "$options": "i"}},
                {"first_name": {"$regex": f".*{recipient_name}.*", "$options": "i"}},
                {"last_name": {"$regex": f".*{recipient_name}.*", "$options": "i"}},
                {"$or": [
                    {"first_name": {"$regex": f"^{recipient_name.split()[0]}", "$options": "i"}},
                    {"last_name": {"$regex": f"{recipient_name.split()[-1]}$", "$options": "i"}}
                ]} if " " in recipient_name else {}
            ]
        }
        
        if query:
            # ถ้ามีทั้ง room query และ name query ให้รวมด้วย $and
            query = {"$and": [query, name_query]}
        else:
            query = name_query
    
    if not query:
        return None
    
    print(f"🔍 Searching user with query: {query}")
    user = users_col.find_one(query)
    
    if user:
        print(f"✅ Found user: {user.get('display_name')} (Room: {user.get('room_number')})")
    else:
        print(f"❌ User not found")
    
    return user

def find_users_by_name_fuzzy(name):
    """ค้นหาผู้ใช้จากชื่อแบบ fuzzy match"""
    if not name or name == "-":
        return []
    
    # ค้นหาชื่อที่ใกล้เคียงในฐานข้อมูล
    users = list(users_col.find({
        "$or": [
            {"first_name": {"$regex": name, "$options": "i"}},
            {"last_name": {"$regex": name, "$options": "i"}},
            {"display_name": {"$regex": name, "$options": "i"}}
        ]
    }).limit(10))
    
    return users

# ================= AI & RAG HELPERS (MODIFIED) =================

# [UPDATED PROMPT] เพิ่มกฎให้ตอบตามรูปแบบเป๊ะๆ
CHAT_SYSTEM_PROMPT = """
คุณคือ "น้องบอตนิติ" ผู้ช่วยคอนโดลุมพินี พาร์ค
หน้าที่: ตอบคำถามลูกบ้านด้วยความสุภาพ สดใส และช่วยเหลือข้อมูลตามจริง

กฎการตอบ (Strict Rules):
1. **ลำดับความสำคัญ:** 
   - ให้โฟกัสและตอบ "คำถามล่าสุดของผู้ใช้" ให้ตรงประเด็นที่สุดก่อน
   - **ห้าม** แทรกเรื่องพัสดุหรือสถานะการร้องเรียน หากผู้ใช้ถามเรื่องอื่น (เช่น กฎระเบียบ, เบอร์โทร, วิธีใช้) ให้ตอบเรื่องนั้นเพียวๆ
   - **ห้าม** นำข้อมูลส่วน "รายการพัสดุ:" หรือ "ประวัติแจ้งร้องเรียน" มาตอบเมื่อผู้ใช้ไม่ได้ถามถึง
   - ให้แจ้งเตือนพัสดุ/งานร้องเรียน ก็ต่อเมื่อ:
     ก. ผู้ใช้ถามถึงโดยเฉพาะ (เช่น "มีของมาส่งไหม", "สถานะร้องเรียนถึงไหน", "มีพัสดุไหม")
     ข. **เท่านั้น** ไม่ต้องแจ้งพัสดุเมื่อผู้ใช้แค่ทักทาย (เช่น "สวัสดี") หรือถามเรื่องทั่วไป

2. **การตอบเรื่องพัสดุ:**
   - หากใน Context มีข้อมูลส่วน "รายการพัสดุ:" และผู้ใช้ถามถึงพัสดุโดยเฉพาะ ให้ Copy ข้อความในส่วนนั้นมาตอบผู้ใช้ **ทั้งดุ้น** ทันที (ห้ามสรุปใหม่ ห้ามเปลี่ยนคำ)

3. **ข้อมูลส่วนตัว:** ยึดข้อมูลใน [Context] อย่างเคร่งครัด
   - ถ้า Context ระบุ "ไม่มีประวัติการแจ้งร้องเรียน" ห้ามพูดถึงสถานะการร้องเรียน
   - ถ้า Context ไม่มีข้อมูลพัสดุ (หรือระบุว่าไม่มีพัสดุ) ห้ามสร้างข้อมูลพัสดุขึ้นมาเอง

4. **ขอบเขต:** หากถามเรื่องที่ไม่มีข้อมูล ให้ตอบว่า "ขออภัยค่ะ ไม่มีข้อมูลส่วนนี้ รบกวนติดต่อสำนักงานนิติฯ อาคาร A ชั้น G หรือโทร 02-689-6888 เพื่อสอบถามเพิ่มเติมนะคะ"

5. **[CRITICAL] ความเป็นส่วนตัวผู้อื่น:** 
   - ห้ามเปิดเผย หรือตรวจสอบข้อมูลของ "ห้องอื่น" หรือ "บุคคลอื่น" เด็ดขาด

6. **การขึ้นบรรทัดใหม่ในการตอบ:** 
   - ขึ้นบรรทัดใหม่ให้สวยงามเมื่อจำเป็น จากข้อความยาวๆติดกันเป็นแถบยาว ให้ขึ้นบรรทัดใหม่บ้างให้สวยงาม

7. **[IMPORTANT] การตอบคำทักทาย:**
   - เมื่อผู้ใช้ทักทายง่ายๆ (เช่น "สวัสดี", "hello") ให้ตอบทักทายกลับแบบสุภาพ และอาจแนะนำตัวย่อๆ เท่านั้น
   - **ห้าม** นำข้อมูลพัสดุหรือประวัติร้องเรียนมาตอบในคำทักทายง่ายๆ
   - ตัวอย่างการตอบที่ถูกต้อง: "สวัสดีค่ะคุณ[ชื่อ] มีอะไรให้ช่วยเหลือคะ?" หรือ "สวัสดีครับ ยินดีต้อนรับค่ะ"

8. **[NEW RULE] การแยกแยะการถามเกี่ยวกับกฎ vs การแจ้งร้องเรียน:**
   - เมื่อผู้ใช้ถามเกี่ยวกับ "กฎการแจ้งร้องเรียน", "รายละเอียดการแจ้งร้องเรียน", "วิธีแจ้งร้องเรียน" ให้ตอบเฉพาะข้อมูลวิธีการแจ้งร้องเรียนเท่านั้น
   - **ห้าม** เข้าสู่โหมดแจ้งร้องเรียนจริงเมื่อผู้ใช้ถามเกี่ยวกับกฎหรือวิธีการ
   - ตัวอย่างที่ถูกต้อง: ตอบข้อมูลจากคลังความรู้เกี่ยวกับวิธีการแจ้งร้องเรียน
   - ตัวอย่างที่ผิด: เริ่มกระบวนการแจ้งร้องเรียนด้วยการถาม "รับทราบค่ะ 📝 พิมพ์แจ้งรายละเอียดการร้องเรียนได้เลยค่ะ"

9. **[NEW RULE] การตอบเกี่ยวกับข้อมูลทั่วไป:**
   - เมื่อผู้ใช้ถามเรื่องทั่วไป (เช่น กฎระเบียบ, เบอร์โทรศัพท์, วิธีใช้บริการ) ให้ตอบเฉพาะข้อมูลที่เกี่ยวข้องเท่านั้น
   - **ห้าม** นำข้อมูลส่วนตัวของผู้ใช้ (เช่น พัสดุ, ประวัติร้องเรียน) มาตอบในบริบทนี้
   - ถ้าผู้ใช้ถามหลายหัวข้อในครั้งเดียว (เช่น กฎระเบียบและเบอร์โทรฉุกเฉิน) ให้ตอบครบทุกหัวข้อที่ถาม แต่ห้ามเพิ่มข้อมูลที่ไม่เกี่ยวข้อง
"""

def get_knowledge_context(user_text, user):
    """
    ดึงข้อมูล Context ทั้งหมด:
    1. ข้อมูลส่วนตัว (Users)
    2. พัสดุของห้องตัวเอง (Parcels) - [FORMAT UPDATED]
    3. การแจ้งร้องเรียนของตัวเอง (Complaints)
    4. ความรู้ทั่วไป (Knowledge Base)
    """
    context_parts = []
    
    try:
        # --- PART 1: ข้อมูลส่วนตัว (Personal Data) ---
        user_info = f"ผู้ใช้งาน: {user.get('first_name', 'ลูกบ้าน')} {user.get('last_name', '')} (ห้อง {user.get('room_number', 'ไม่ระบุ')})"
        
        # 1.1 Parcels (ดูเฉพาะห้องตัวเอง) - [UPDATED FORMAT]
        # ข้อมูลพัสดุจะถูกนำไปใช้ในฟังก์ชัน process_text_logic เท่านั้น
        parcel_context = f"รายการพัสดุ:\n🏠 ห้อง {user.get('room_number', '-')}\n📦 ตอนนี้ยังไม่มีพัสดุค้างอยู่นะคะ" # Default ไม่มีพัสดุ
        
        if user.get('room_number'):
            my_parcels = list(parcels_col.find({"room_number": user['room_number'], "status": "pending"}))
            if my_parcels:
                count = len(my_parcels)
                # Header สำหรับมีพัสดุ
                p_str = f"รายการพัสดุ:\n🏠 ห้อง {user['room_number']}\n📦 มีพัสดุคงค้างทั้งหมด {count} ชิ้น\n"
                
                item_lines = []
                for idx, p in enumerate(my_parcels, 1):
                    # Format: 1. บริษัทขนส่ง: ... | เลขพัสดุ: ... | PIN: ...
                    line = f"{idx}. บริษัทขนส่ง: {p.get('transport')} | เลขพัสดุ: {p.get('tracking_number')} | PIN: {p.get('pin')}"
                    item_lines.append(line)
                
                p_str += "\n".join(item_lines)
                p_str += "\nถ้าจะรับพัสดุแจ้ง PIN ให้พนักงานได้เลยนะคะ"
                
                parcel_context = p_str
        
        # 1.2 Complaints (ดูเฉพาะ ID ตัวเอง - 3 รายการล่าสุด)
        complaint_context = "ประวัติการแจ้งร้องเรียน: ไม่มีประวัติการแจ้งร้องเรียนล่าสุด (ระบบปกติ)"
        my_complaints = list(complaints_col.find({"line_user_id": user['line_user_id']}).sort("timestamp", -1).limit(3))
        if my_complaints:
            c_list = []
            for c in my_complaints:
                status_th = {
                    "waiting_image": "รอรูปภาพ",
                    "pending": "รอดำเนินการ",
                    "resolved": "เสร็จสิ้น"
                }.get(c.get('status'), c.get('status'))
                c_list.append(f"- เรื่อง: {c.get('description')} (สถานะ: {status_th})")
            complaint_context = "ประวัติแจ้งร้องเรียนล่าสุด:\n" + "\n".join(c_list)

        personal_data_str = (
            f"[ข้อมูลส่วนตัวของผู้ใช้ (Private Data)]\n"
            f"{user_info}\n"
            f"{parcel_context}\n"
            f"{complaint_context}\n"
        )
        context_parts.append(personal_data_str)

        # --- PART 2: ความรู้ทั่วไป (Knowledge Base - RAG) ---
        analysis_prompt = f"""
        จงวิเคราะห์ข้อความ: "{user_text}" สกัด keywords ภาษาไทย 2-3 คำ คั่นด้วยช่องว่าง
        """
        keyword_res = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=analysis_prompt
        )
        ai_keywords = keyword_res.text.strip().split()
        
        # ค้นหาใน Knowledge Base
        all_docs = list(kb_col.find())
        found_results = []

        for doc in all_docs:
            content = str(doc.get('content', '')).lower()
            topic = str(doc.get('topic', '')).lower()
            score = 0
            
            for kw in ai_keywords:
                kw = kw.lower()
                if kw in content: score += 10
                if kw in topic: score += 5
            
            if user_text.strip() in content: score += 20
            
            if score > 0:
                found_results.append((score, f"หัวข้อ: {doc.get('topic')}\nรายละเอียด: {doc.get('content')}"))

        found_results.sort(key=lambda x: x[0], reverse=True)
        
        kb_str = ""
        if found_results:
            kb_content = "\n---\n".join([item[1] for item in found_results[:3]])
            kb_str = f"[คลังความรู้ทั่วไป (Knowledge Base)]\n{kb_content}"
        
        if kb_str:
            context_parts.append(kb_str)
            
        return "\n\n".join(context_parts)

    except Exception as e:
        print(f"RAG Error: {e}")
        return None

def analyze_intent(text):
    try:
        # ตรวจสอบก่อนว่าผู้ใช้ถามเกี่ยวกับ "กฎ" หรือ "รายละเอียด"
        rule_keywords = ["กฎการแจ้งร้องเรียน", "กฎการร้องเรียน", "รายละเอียดการแจ้งร้องเรียน", 
                        "วิธีแจ้งร้องเรียน", "ขั้นตอนการแจ้งร้องเรียน", "ขอทราบการแจ้งร้องเรียน",
                        "อยากทราบการแจ้งร้องเรียน", "อยากรู้การแจ้งร้องเรียน",
                        # เพิ่มคำค้นหาให้ครอบคลุมมากขึ้น
                        "กฎแจ้งร้องเรียน", "วิธีร้องเรียน", "ขั้นตอนร้องเรียน",
                        "อยากรู้วิธีแจ้งร้องเรียน", "อยากรู้ขั้นตอนแจ้งร้องเรียน"]
        
        # ถ้าถามเกี่ยวกับกฎหรือรายละเอียด ให้เป็น GENERAL
        if any(keyword in text for keyword in rule_keywords):
            return "GENERAL"
        
        # ตรวจสอบว่าเป็นคำถามทั่วไปที่ไม่ใช่การแจ้งร้องเรียน
        general_keywords = ["สูบบุหรี่", "กฎการจอด", "เบอร์ตำรวจ", "กฎระเบียบ", 
                           "เบอร์โทร", "เบอร์ฉุกเฉิน", "วิธีใช้", "บริการ",
                           "ค่าบริการ", "ทำยังไง", "อย่างไร", "สอบถาม"]
        
        if any(keyword in text for keyword in general_keywords):
            return "GENERAL"
        
        # ใช้ gemini-3-flash-preview
        prompt = f"Classify intent: '{text}' -> Return ONLY: COMPLAINT (แจ้งเรื่องใหม่/แจ้งร้องเรียน), CANCEL (ยกเลิก), CHECK_STATUS (ติดตามงานร้องเรียน), or OTHER (ทักทาย/ถามทั่วไป/ถามกฎระเบียบ/สอบถามข้อมูล)."
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt
        )
        intent_result = response.text.strip().upper()
        
        # ถ้า Gemini ตรวจจับเป็น COMPLAINT แต่ข้อความมีคำว่า "กฎ" หรือ "วิธี" ให้เปลี่ยนเป็น GENERAL
        if intent_result == "COMPLAINT" and any(word in text for word in ["กฎ", "วิธี", "ขั้นตอน", "สอบถาม"]):
            return "GENERAL"
            
        return intent_result
    except: 
        return "OTHER"

def update_chat_history(uid, role, message):
    if role == 'assistant': role = 'model'
    entry = {"role": role, "parts": [message], "timestamp": datetime.datetime.utcnow()}
    users_col.update_one(
        {"line_user_id": uid},
        {"$push": {"chat_history": {"$each": [entry], "$slice": -10}}}
    )
    
    # บันทึกใน chat_history collection ด้วย
    save_full_chat_history(uid, role, message, "line")

def get_gemini_chat_history(uid):
    user = users_col.find_one({"line_user_id": uid})
    history = []
    if user and "chat_history" in user:
        for msg in user["chat_history"]:
            role = msg.get("role")
            raw_parts = msg.get("parts")
            
            if not raw_parts:
                raw_parts = [msg.get("text", "")]
            
            if role == "assistant": role = "model"
            
            formatted_parts = []
            for part in raw_parts:
                if isinstance(part, str):
                    formatted_parts.append({"text": part})
                else:
                    formatted_parts.append(part)
            
            if role and formatted_parts:
                history.append({"role": role, "parts": formatted_parts})
    return history

# ================= 1. เพิ่มฟังก์ชันวิเคราะห์ความสำคัญจากคำอธิบาย (เพิ่มใหม่) =================

def analyze_urgency_from_description(user_desc):
    """
    วิเคราะห์ความสำคัญเบื้องต้นจากข้อความที่ผู้ใช้แจ้ง
    """
    try:
        user_desc_lower = user_desc.lower()
        
        # เงื่อนไขความสำคัญสูง (ต้องแก้ไขวันนี้)
        high_keywords = [
            "ไฟไหม้", "ไฟลุก", "ไฟช็อต", "ไฟฟ้าลัดวงจร", "ไฟดูด", "ไฟสปาร์ค",
            "น้ำท่วม", "น้ำรั่วมาก", "น้ำซึมมาก", "น้ำแตก", "ท่อน้ำแตก", "ท่อประปาแตก",
            "แก๊สรั่ว", "กลิ่นแก๊ส", "แก๊สหอบ", "แก๊สผิดปกติ",
            "โจร", "ขโมย", "ปล้น", "งัดแงะ", "ปล้น", "เข้าไปในห้อง",
            "อันตราย", "ฉุกเฉิน", "ช่วยด่วน", "รีบด่วน", "ด่วนมาก", "เร่งด่วน",
            "บันไดหนีไฟ", "ทางหนีไฟ", "อุปกรณ์ป้องกัน", "ระเบิด", "ลุกไหม้",
            "ไฟฟ้าช็อต", "ไฟดับทั้งอาคาร", "ไฟดับทั้งหมด"
        ]
        
        # เงื่อนไขความสำคัญกลาง (แก้ไขภายใน 1-2 วัน)
        medium_keywords = [
            "แอร์เสีย", "เครื่องปรับอากาศ", "แอร์ไม่เย็น", "แอร์รั่ว", "แอร์น้ำหยด",
            "ไฟฟ้าเสีย", "ไฟไม่ติด", "สวิทช์เสีย", "ปลั๊กไฟเสีย", "เบรกเกอร์",
            "ประตูเสีย", "ล็อคประตู", "กุญแจ", "ประตูเปิดไม่ติด", "ประตูพัง",
            "ปั๊มน้ำ", "น้ำไม่ไหล", "น้ำตัน", "น้ำอ่อนแรง",
            "ส้วมตัน", "ชักโครก", "ท่อตัน", "ชักโครกไม่ลง",
            "เครื่องทำน้ำร้อน", "เครื่องทำน้ำอุ่น", "น้ำไม่ร้อน",
            "ลิฟต์", "ลิฟต์ขัดข้อง", "ลิฟต์ไม่ทำงาน"
        ]
        
        # เงื่อนไขความสำคัญต่ำ (แก้ไขภายใน 3-5 วัน)
        low_keywords = [
            "สีลอก", "ผนังร้าว", "รอยร้าว", "สีแตก", "สีหลุด",
            "ฝ้าเพดาน", "ฝ้ารั่ว", "ฝ้าแตกร้าว", "ฝ้าโก่ง",
            "พื้นกระเทาะ", "พื้นไม้", "พื้นปาร์เก้",
            "หลอดไฟ", "ไฟส่องสว่าง", "ไฟหน่วง", "ไฟกระพริบ",
            "เต้ารับ", "ปลั๊กไฟ", "ปลั๊กหลวม", "ปลั๊กหลุด",
            "ที่จับประตู", "ลูกบิด", "ลูกบิดหลวม",
            "มุ้งลวด", "มุ้งลวดเสีย", "มุ้งลวดฉีก"
        ]
        
        # ตรวจสอบคำสำคัญความสำคัญสูง
        for keyword in high_keywords:
            if keyword in user_desc_lower:
                print(f"🔴 ตรวจพบคำสำคัญ HIGH: '{keyword}' ในคำอธิบาย")
                return "High"
        
        # ตรวจสอบคำสำคัญความสำคัญกลาง
        for keyword in medium_keywords:
            if keyword in user_desc_lower:
                print(f"🟡 ตรวจพบคำสำคัญ MEDIUM: '{keyword}' ในคำอธิบาย")
                return "Medium"
        
        # ตรวจสอบคำสำคัญความสำคัญต่ำ
        for keyword in low_keywords:
            if keyword in user_desc_lower:
                print(f"🟢 ตรวจพบคำสำคัญ LOW: '{keyword}' ในคำอธิบาย")
                return "Low"
        
        print(f"⚪ ไม่พบคำสำคัญที่ตรงกับหมวดหมู่ในคำอธิบาย")
        return None  # ไม่สามารถระบุได้จากข้อความ
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการวิเคราะห์จากคำอธิบาย: {e}")
        return None

# ================= 2. เพิ่มฟังก์ชันตัดสินใจขั้นสุดท้าย (เพิ่มใหม่) =================

def determine_final_urgency(desc_urgency, ai_urgency, user_desc):
    """
    กำหนดความสำคัญขั้นสุดท้ายโดยพิจารณาจากทั้งสองแหล่ง
    """
    try:
        user_desc_lower = user_desc.lower()
        
        # 🔥 กฎพิเศษ: ถ้ามีคำว่า "ไฟไหม้" ให้เป็น High เสมอ
        if "ไฟไหม้" in user_desc_lower or "ไฟลุก" in user_desc_lower or "ไฟฟ้าลัดวงจร" in user_desc_lower:
            print(f"🔥 กฎพิเศษ: คำอธิบายมี 'ไฟไหม้' -> กำหนดเป็น HIGH")
            return "High"
        
        # 🔥 กฎพิเศษ: ถ้ามีคำว่าร้ายแรงอื่นๆ
        emergency_keywords = ["น้ำท่วม", "แก๊สรั่ว", "ระเบิด", "ไฟฟ้าช็อต"]
        for keyword in emergency_keywords:
            if keyword in user_desc_lower:
                print(f"🔥 กฎพิเศษ: คำอธิบายมี '{keyword}' -> กำหนดเป็น HIGH")
                return "High"
        
        # ถ้าทั้งสองแหล่งเห็นตรงกัน
        if desc_urgency == ai_urgency:
            print(f"✅ ทั้งสองแหล่งตรงกัน: {desc_urgency}")
            return desc_urgency
        
        # หากแหล่งหนึ่งระบุ High อีกแหล่งระบุต่ำกว่า -> ให้เป็น High
        if desc_urgency == "High" or ai_urgency == "High":
            print(f"⚠️  หนึ่งในแหล่งระบุ HIGH -> กำหนดเป็น HIGH")
            return "High"
        
        # หากแหล่งหนึ่งระบุ Medium
        if desc_urgency == "Medium" or ai_urgency == "Medium":
            print(f"📌  หนึ่งในแหล่งระบุ MEDIUM -> กำหนดเป็น MEDIUM")
            return "Medium"
        
        # นอกนั้นเป็น Low หรือไม่พบข้อมูล
        print(f"📝  ไม่มีข้อมูลชัดเจน -> กำหนดเป็น LOW")
        return "Low"
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการตัดสินใจขั้นสุดท้าย: {e}")
        return "Medium"  # ค่า default

# ================= USER FUNCTIONS =================

def get_or_create_user(user_id, platform="line", display_name=None, picture_url=None):
    user = users_col.find_one({"line_user_id": user_id})
    
    update_data = {
        "last_active": datetime.datetime.utcnow(),
        "platform": platform
    }
    if display_name: update_data["display_name"] = display_name
    if picture_url: update_data["picture_url"] = picture_url

    if not user:
        new_user = {
            "line_user_id": user_id,
            "first_name": None, "last_name": None, 
            "room_number": None, "phone_number": None,
            "complaint_state": "normal",
            "current_complaint_id": None,
            "draft_desc": None,
            "chat_history": [],
            "display_name": display_name if display_name else "Unknown",
            "picture_url": picture_url,
            **update_data
        }
        users_col.insert_one(new_user)
        return new_user
    else:
        users_col.update_one({"line_user_id": user_id}, {"$set": update_data})
        return users_col.find_one({"line_user_id": user_id})

def is_registered(user):
    """
    ตรวจสอบว่าผู้ใช้ลงทะเบียนครบถ้วนหรือไม่
    ต้องมี: first_name, last_name, room_number, phone_number
    """
    required_fields = ['first_name', 'last_name', 'room_number', 'phone_number']
    
    for field in required_fields:
        value = user.get(field)
        # ตรวจสอบว่ามีค่าและไม่ใช่ค่า None, ไม่ใช่ string ว่าง
        if not value or str(value).strip() == '' or str(value).strip().lower() == 'none':
            return False
    
    return True

def handle_registration(user, text):
    parts = text.split()
    if len(parts) != 5:
        current_name = user.get('display_name', 'ลูกบ้าน')
        return (
            f"สวัสดีคุณ {current_name}! 👋\n\n"
            f"📝 กรุณาลงทะเบียนเพื่อใช้งานแชตบอตนิติบุคคล\n\n"
            f"พิมพ์: ลงทะเบียน [เลขห้อง] [ชื่อ] [นามสกุล] [เบอร์โทร]\n\n"
            f"ตัวอย่าง:\n"
            f"ลงทะเบียน 814 สมชาย ใจดี 0812345678"
        )

    room, fname, lname, phone = parts[1], parts[2], parts[3], parts[4]
    
    # ตรวจสอบเบอร์โทรซ้ำ
    if users_col.find_one({"phone_number": phone, "line_user_id": {"$ne": user['line_user_id']}}):
        return f"⛔ เบอร์ {phone} มีผู้ใช้แล้วค่ะ"
    
    # ตรวจสอบห้องซ้ำ
    if users_col.find_one({"room_number": room, "line_user_id": {"$ne": user['line_user_id']}}):
        return f"⛔ ห้อง {room} มีผู้ใช้แล้วค่ะ"
    
    # อัพเดตข้อมูลลงทะเบียน
    users_col.update_one({"line_user_id": user['line_user_id']}, {"$set": {
        "first_name": fname, 
        "last_name": lname, 
        "room_number": room, 
        "phone_number": phone
    }})
    
    # ดึงข้อมูลผู้ใช้ที่อัพเดตแล้ว
    updated_user = users_col.find_one({"line_user_id": user['line_user_id']})
    
    # ✅ บันทึก Audit Log สำหรับการลงทะเบียน
    log_admin_action(
        action="User Registration",
        performed_by=f"System ({updated_user.get('platform', 'unknown')})",
        target=f"User: {fname} {lname} (Room: {room})",
        details=f"Registered via {updated_user.get('platform', 'unknown')} platform"
    )
    
    return (
        f"✅ ลงทะเบียนสำเร็จ!\n"
        f"🏠 ห้อง: {room}\n"
        f"👤 ชื่อ: {fname} {lname}\n"
        f"📞 เบอร์: {phone}\n\n"
        f"ตอนนี้คุณสามารถใช้งานแชตบอตได้เต็มรูปแบบแล้วค่ะ 🎉"
    )

# ================= LOGIC HANDLER (แก้ไขส่วนสำคัญ) =================

def process_text_logic(user, text):
    uid = user['line_user_id']
    state = user.get('complaint_state', 'normal')
    platform = user.get('platform', 'line')  # ดึงข้อมูล platform

    if text.startswith("ลงทะเบียน"): 
        return handle_registration(user, text)
    
    if not is_registered(user):
        current_name = user.get('display_name', 'ลูกบ้าน')
        return (
            f"สวัสดีคุณ {current_name}! 👋\n\n"
            f"📝 กรุณาลงทะเบียนเพื่อใช้งานแชตบอตนิติบุคคล\n\n"
            f"พิมพ์: ลงทะเบียน [เลขห้อง] [ชื่อ] [นามสกุล] [เบอร์โทร]\n\n"
            f"ตัวอย่าง:\n"
            f"ลงทะเบียน 814 สมชาย ใจดี 0812345678"
        )
    
    # ตรวจสอบก่อนว่าผู้ใช้ถามเกี่ยวกับ "กฎ" หรือ "รายละเอียด" ของการแจ้งร้องเรียน
    rule_keywords = ["กฎการแจ้งร้องเรียน", "กฎการร้องเรียน", "รายละเอียดการแจ้งร้องเรียน", 
                     "วิธีแจ้งร้องเรียน", "ขั้นตอนการแจ้งร้องเรียน", "ขอทราบการแจ้งร้องเรียน",
                     "อยากทราบการแจ้งร้องเรียน", "อยากรู้การแจ้งร้องเรียน",
                     "กฎแจ้งร้องเรียน", "วิธีร้องเรียน", "ขั้นตอนร้องเรียน",
                     "อยากรู้วิธีแจ้งร้องเรียน", "อยากรู้ขั้นตอนแจ้งร้องเรียน"]
    
    general_keywords = ["สูบบุหรี่", "กฎการจอด", "เบอร์ตำรวจ", "กฎระเบียบ", 
                       "เบอร์โทร", "เบอร์ฉุกเฉิน", "วิธีใช้", "บริการ",
                       "ค่าบริการ", "ทำยังไง", "อย่างไร", "สอบถาม"]
    
    # ตรวจสอบว่าเป็นคำถามเกี่ยวกับกฎหรือรายละเอียดเท่านั้น (ไม่ใช่การแจ้งร้องเรียนจริง)
    is_asking_about_rules = any(keyword in text for keyword in rule_keywords)
    
    # ตรวจสอบว่าเป็นคำถามทั่วไปที่ไม่ใช่การแจ้งร้องเรียน
    is_general_inquiry = any(keyword in text for keyword in general_keywords)
    
    # ถ้าถามเกี่ยวกับกฎหรือรายละเอียด หรือเป็นคำถามทั่วไป ให้ถือว่าเป็น general_topic
    if is_asking_about_rules or is_general_inquiry:
        # ดึงข้อมูลจาก Knowledge Base เท่านั้น
        try:
            all_docs = list(kb_col.find())
            kb_content = ""
            for doc in all_docs:
                topic_lower = str(doc.get('topic', '')).lower()
                content_lower = str(doc.get('content', '')).lower()
                text_lower = text.lower()
                
                # หาข้อมูลที่เกี่ยวข้องกับการแจ้งร้องเรียน (ถ้าถามเกี่ยวกับกฎ)
                if is_asking_about_rules:
                    if any(word in topic_lower for word in ["แจ้งร้องเรียน", "ร้องเรียน", "วิธีแจ้ง"]):
                        kb_content += f"หัวข้อ: {doc.get('topic')}\nรายละเอียด: {doc.get('content')}\n---\n"
                
                # หาข้อมูลที่เกี่ยวข้องกับคำถามทั่วไป
                if is_general_inquiry:
                    # ตรวจสอบว่ามีหัวข้อที่ตรงกับคำถาม
                    topic_match = any(keyword.lower() in topic_lower for keyword in general_keywords)
                    content_match = any(keyword.lower() in content_lower for keyword in general_keywords)
                    
                    if topic_match or content_match:
                        kb_content += f"หัวข้อ: {doc.get('topic')}\nรายละเอียด: {doc.get('content')}\n---\n"
            
            if kb_content:
                context_msg = f"\n[Context]:\n[คลังความรู้ทั่วไป (Knowledge Base)]\n{kb_content}\n"
            else:
                context_msg = f"\n[Context]:\nไม่มีข้อมูลเกี่ยวกับเรื่องนี้ในคลังความรู้\n"
            
            history = get_gemini_chat_history(uid)
            try:
                chat = client.chats.create(
                    model='gemini-3-flash-preview',
                    config=types.GenerateContentConfig(system_instruction=CHAT_SYSTEM_PROMPT),
                    history=history
                )
                res = chat.send_message(f"{text}\n{context_msg}")
                return res.text.strip()
            except Exception as e:
                print(f"Chat Error: {e}")
                return "ขออภัย ระบบขัดข้องชั่วคราวค่ะ"
                
        except Exception as e:
            print(f"General topic context error: {e}")
            return "ขออภัยค่ะ เกิดข้อผิดพลาดในการดึงข้อมูล"
    
    # ================= แก้ไขส่วนสำคัญ: เพิ่มการตรวจสอบความตั้งใจแบบละเอียด =================
    
    # 1. ตรวจสอบว่าผู้ใช้ต้องการเริ่มต้นกระบวนการแจ้งร้องเรียน (รวมถึงการพิมพ์ผิด)
    # ขยายรายการคำที่ต้องการเริ่มต้นกระบวนการ (รวมคำพิมพ์ผิดที่พบบ่อย)
    complaint_start_keywords = [
        "แจ้งร้องเรียน", "ร้องเรียน", "แจ้งเรื่อง", "แจ้งปัญหา", "เเจ้งร้องเรียน",
        "แจ้งเรื่อง", "เเจ้งปัญหา", "เเจ้งปัญหา", "เเจ้ง", "แจ้ง", "มีปัญหา",
        "มีเรื่อง", "ขอเเจ้ง", "ขอแจ้ง", "ต้องการร้องเรียน", "อยากร้องเรียน",
        "อยากเเจ้ง", "อยากเเจ้ง", "ขอร้องเรียน", "ต้องการเเจ้ง", "ต้องการแจ้ง",
        # เพิ่มคำที่อาจพิมพ์ผิด
        "เเจ่งร้องเรียน", "แจ้งร้องเรีน", "แจ้งร้องเรย", "แจ้งร้องเรี่ยน",
        "แจ้งร้องเรัยน", "แจ้งร้องเรีนน", "แจ้งร้องเรียนน"
    ]
    
    # 2. ตรวจสอบว่าข้อความคล้ายกับคำเริ่มต้นกระบวนการ (ใช้การเปรียบเทียบแบบไม่ซีเรียสเกินไป)
    text_lower = text.strip().lower()
    is_complaint_start = False
    complaint_start_word = None
    
    # ตรวจสอบแบบ exact match ก่อน
    if text_lower in [kw.lower() for kw in complaint_start_keywords]:
        is_complaint_start = True
        complaint_start_word = text_lower
    else:
        # ตรวจสอบแบบ partial match (ถ้าข้อความสั้นและคล้ายกับคำเริ่มต้น)
        if len(text_lower) <= 20:  # ข้อความไม่ยาวเกินไป
            for keyword in complaint_start_keywords:
                keyword_lower = keyword.lower()
                # ตรวจสอบความคล้ายคลึงแบบง่าย
                if (keyword_lower in text_lower or 
                    text_lower in keyword_lower or
                    sum(1 for a, b in zip(text_lower, keyword_lower) if a == b) / max(len(text_lower), len(keyword_lower)) > 0.7):
                    is_complaint_start = True
                    complaint_start_word = keyword
                    break
    
    # ถ้าผู้ใช้พิมพ์คำว่าเริ่มต้นกระบวนการร้องเรียน (หรือคำที่คล้ายกัน)
    if is_complaint_start:
        if state == 'normal':
            users_col.update_one({"line_user_id": uid}, {"$set": {"complaint_state": "filing_desc"}})
            return "รับทราบค่ะ 📝 พิมพ์แจ้งรายละเอียดการร้องเรียนได้เลยค่ะ"
    
    # ตรวจสอบว่าผู้ใช้ต้องการเริ่มต้นกระบวนการแจ้งร้องเรียนด้วย AI intent
    intent = analyze_intent(text)
    
    # ================= ส่วนที่แก้ไข: ใช้ AI ช่วยตัดสินใจ =================
    
    # ตรวจสอบสถานะและดำเนินการตาม intent
    if intent == "CANCEL" or text.lower() in ["ยกเลิก", "cancel"]:
        users_col.update_one(
            {"line_user_id": uid}, 
            {"$set": {"complaint_state": "normal", "draft_desc": None}}
        )
        return "❌ ยกเลิกรายการให้แล้วค่ะ"

    # ถ้า AI ตัดสินว่าเป็น COMPLAINT และผู้ใช้อยู่ในสถานะปกติ
    if intent == "COMPLAINT":
        if state == 'normal':
            # ✅ แก้ไข: ใช้ AI ช่วยตรวจสอบว่าควรเริ่มกระบวนการหรือเป็นรายละเอียด
            # ถ้าข้อความสั้นและดูเหมือนคำสั่งเริ่มต้น ให้เริ่มกระบวนการ
            if len(text.strip()) <= 30:  # ข้อความไม่ยาวเกินไป
                # ใช้ AI ช่วยตรวจสอบเพิ่มเติม
                check_prompt = f"ข้อความนี้ '{text}' เป็นการเริ่มต้นการแจ้งร้องเรียนหรือรายละเอียดการร้องเรียน? ตอบแค่ 'เริ่มต้น' หรือ 'รายละเอียด'"
                try:
                    check_res = client.models.generate_content(
                        model='gemini-3-flash-preview',
                        contents=check_prompt
                    )
                    ai_check = check_res.text.strip().lower()
                    
                    if "เริ่มต้น" in ai_check:
                        users_col.update_one({"line_user_id": uid}, {"$set": {"complaint_state": "filing_desc"}})
                        return "รับทราบค่ะ 📝 พิมพ์แจ้งรายละเอียดการร้องเรียนได้เลยค่ะ"
                    else:
                        # ถ้าเป็นรายละเอียด ให้บันทึกและขอรูปภาพทันที
                        users_col.update_one(
                            {"line_user_id": uid}, 
                            {"$set": {"complaint_state": "waiting_image", "draft_desc": text}}
                        )
                        return f"บันทึกรายละเอียด '{text[:50]}...' แล้วค่ะ 📝\n\n📸 กรุณาส่งรูปภาพประกอบการร้องเรียน (กดปุ่มแนบรูปภาพ)"
                except Exception as e:
                    print(f"AI check error: {e}")
                    # ถ้า AI ตรวจสอบไม่ได้ ให้ใช้วิธีเดิม (บันทึกเป็นรายละเอียด)
                    users_col.update_one(
                        {"line_user_id": uid}, 
                        {"$set": {"complaint_state": "waiting_image", "draft_desc": text}}
                    )
                    return f"บันทึกรายละเอียด '{text[:50]}...' แล้วค่ะ 📝\n\n📸 กรุณาส่งรูปภาพประกอบการร้องเรียน (กดปุ่มแนบรูปภาพ)"
            else:
                # ถ้าข้อความยาว ให้ถือว่าเป็นรายละเอียด
                users_col.update_one(
                    {"line_user_id": uid}, 
                    {"$set": {"complaint_state": "waiting_image", "draft_desc": text}}
                )
                return f"บันทึกรายละเอียด '{text[:50]}...' แล้วค่ะ 📝\n\n📸 กรุณาส่งรูปภาพประกอบการร้องเรียน (กดปุ่มแนบรูปภาพ)"

    if state == 'filing_desc':
        users_col.update_one(
            {"line_user_id": uid}, 
            {"$set": {"complaint_state": "waiting_image", "draft_desc": text}}
        )
        return f"บันทึกรายละเอียด '{text[:50]}...' แล้วค่ะ 📝\n\n📸 กรุณาส่งรูปภาพประกอบการร้องเรียน (กดปุ่มแนบรูปภาพ)"

    if state == 'waiting_image':
        return "📸 รอรูปภาพประกอบการร้องเรียนค่ะ (หรือพิมพ์ 'ยกเลิก' เพื่อล้างรายการ)"

    # สำหรับ OTHER, GENERAL และ CHECK_STATUS ให้ใช้ AI ตอบตามปกติ
    # ตรวจสอบว่าเป็นคำทักทายง่ายๆ (ไม่ต้องการแจ้งพัสดุ)
    greeting_words = ["สวัสดี", "หวัดดี", "hello", "hi", "สวัสดีค่ะ", "สวัสดีครับ", "ดี", "ดีจ้า"]
    is_simple_greeting = text.strip().lower() in [g.lower() for g in greeting_words]
    
    # ตรวจสอบว่าเป็นคำถามทั่วไปที่ไม่ต้องการแจ้งพัสดุ
    general_topics = ["กฎระเบียบ", "เบอร์โทร", "เบอร์ฉุกเฉิน", "วิธีใช้", "บริการ", "ค่าบริการ", 
                     "ค่าใช้จ่าย", "อัตราค่าบริการ", "ทำยังไง", "อย่างไร"]
    is_general_topic = any(topic in text for topic in general_topics)
    
    # ถ้าถามเรื่องทั่วไปหรือเป็นคำทักทายง่ายๆ ให้ไม่แจ้งพัสดุ
    if is_general_topic or is_simple_greeting:
        # ดึงเฉพาะข้อมูลความรู้ทั่วไป ไม่รวมข้อมูลส่วนตัว
        try:
            # ดึงข้อมูลจาก Knowledge Base เท่านั้น
            all_docs = list(kb_col.find())
            kb_content = ""
            for doc in all_docs:
                topic_lower = str(doc.get('topic', '')).lower()
                content_lower = str(doc.get('content', '')).lower()
                
                # ถ้าเป็นคำทักทายง่ายๆ ให้เอาเฉพาะข้อมูลทักทาย/แนะนำ
                if is_simple_greeting:
                    if any(word in topic_lower for word in ["แนะนำ", "วิธีใช้", "เริ่มต้น", "เมนู"]):
                        kb_content += f"หัวข้อ: {doc.get('topic')}\nรายละเอียด: {doc.get('content')}\n---\n"
                # ถ้าเป็นคำถามทั่วไป ให้เอาเฉพาะข้อมูลที่เกี่ยวข้อง
                elif is_general_topic:
                    for topic in general_topics:
                        if topic in topic_lower or topic in content_lower:
                            kb_content += f"หัวข้อ: {doc.get('topic')}\nรายละเอียด: {doc.get('content')}\n---\n"
                            break
            
            if kb_content:
                context_msg = f"\n[Context]:\n[คลังความรู้ทั่วไป (Knowledge Base)]\n{kb_content}\n"
            else:
                # ถ้าไม่เจอข้อมูลใน KB ให้ใช้ context ว่างๆ
                if is_simple_greeting:
                    context_msg = f"\n[Context]:\nผู้ใช้งาน: {user.get('first_name', 'ลูกบ้าน')} {user.get('last_name', '')} (ห้อง {user.get('room_number', 'ไม่ระบุ')})\n"
                else:
                    context_msg = f"\n[Context]:\nไม่มีข้อมูลเกี่ยวกับเรื่องนี้ในคลังความรู้\n"
        except Exception as e:
            print(f"General topic context error: {e}")
            context_msg = ""
    else:
        # ดึงข้อมูล context ปกติ (รวมพัสดุและข้อมูลส่วนตัว)
        rag_context = get_knowledge_context(text, user)
        context_msg = f"\n[Context]:\n{rag_context}\n" if rag_context else ""
    
    history = get_gemini_chat_history(uid)
    try:
        chat = client.chats.create(
            model='gemini-3-flash-preview',
            config=types.GenerateContentConfig(system_instruction=CHAT_SYSTEM_PROMPT),
            history=history
        )
        res = chat.send_message(f"{text}\n{context_msg}")
        return res.text.strip()
    except Exception as e:
        print(f"Chat Error: {e}")
        return "ขออภัย ระบบขัดข้องชั่วคราวค่ะ"

# ================= LINE WEBHOOK =================

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try: line_handler.handle(body, signature)
    except InvalidSignatureError: return 'Invalid signature', 400
    return 'OK'

@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    uid = event.source.user_id
    with ApiClient(line_configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        try:
            profile = line_bot_api.get_profile(uid)
            display_name = profile.display_name
            picture_url = profile.picture_url
        except:
            display_name = "Line User"
            picture_url = None

        user = get_or_create_user(uid, "line", display_name, picture_url)
        
        update_chat_history(uid, 'user', event.message.text)
        reply = process_text_logic(user, event.message.text)
        update_chat_history(uid, 'model', reply)
        
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))

# ================= 3. แก้ไขฟังก์ชัน handle_image_message (เปลี่ยนข้อความ) =================

@line_handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    uid = event.source.user_id
    with ApiClient(line_configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        blob_client = MessagingApiBlob(api_client)
        
        user = users_col.find_one({"line_user_id": uid})
        
        if user.get('complaint_state') == 'waiting_image' and user.get('draft_desc'):
            msg_content = blob_client.get_message_content(event.message.id)
            
            # Save temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tf:
                tf.write(msg_content)
                temp_path = tf.name
            
            try:
                # 1. Upload to Cloudinary (เก็บรูปไว้ดูเอง)
                up_res = cloudinary.uploader.upload(
                    temp_path,
                    folder="complaints",
                    tags=["complaint", f"user:{uid}"]
                )
                img_url = up_res.get('secure_url')
                user_desc = user.get('draft_desc')
                
                print(f"📸 เริ่มประมวลผลการแจ้งร้องเรียน:")
                print(f"   ผู้ใช้: {user.get('first_name', 'Unknown')} (ห้อง {user.get('room_number', '-')})")
                print(f"   คำอธิบาย: {user_desc}")
                
                # 2. วิเคราะห์ความสำคัญจากคำอธิบาย
                desc_urgency = analyze_urgency_from_description(user_desc)
                print(f"   ความสำคัญจากคำอธิบาย: {desc_urgency}")
                
                # 3. AI Analysis
                ai_summary_text = user_desc 
                ai_urgency = "Medium"  # default

                try:
                    print("🤖 อัพโหลดภาพไปยัง Gemini...")
                    
                    upload_file = client.files.upload(file=temp_path)
                    
                    # รอให้ไฟล์พร้อมใช้งาน
                    while upload_file.state.name == "PROCESSING":
                        time.sleep(1)
                        upload_file = client.files.get(name=upload_file.name)

                    # 🔥 ปรับปรุง Vision Prompt ให้ละเอียดขึ้น
                    vision_prompt = (
                        f"คำอธิบายจากลูกบ้าน: '{user_desc}'\n\n"
                        
                        "📋 วิเคราะห์รูปภาพนี้ประกอบกับคำอธิบายข้างต้น:\n\n"
                        
                        "เกณฑ์ความสำคัญ:\n"
                        "🔴 HIGH (ต้องแก้ไขภายในวันนี้):\n"
                        "   • ไฟไหม้ ไฟฟ้าลัดวงจร ไฟช็อต\n"
                        "   • น้ำท่วมในห้อง ระบบประปาแตก\n"
                        "   • แก๊สรั่ว กลิ่นแก๊ส\n"
                        "   • ทางหนีไฟอุดตัน\n"
                        "   • ประตูหน้าต่างเสียหายจนปิดล็อคไม่ได้\n\n"
                        
                        "🟡 MEDIUM (แก้ไขได้ภายใน 1-2 วัน):\n"
                        "   • เครื่องปรับอากาศเสีย\n"
                        "   • ระบบไฟฟ้าบางส่วนเสีย\n"
                        "   • ประตูล็อคขัดข้อง\n"
                        "   • ปั๊มน้ำไม่ทำงาน\n"
                        "   • ส้วมตัน\n"
                        "   • เครื่องทำน้ำร้อนเสีย\n\n"
                        
                        "🟢 LOW (แก้ไขได้ภายใน 3-5 วัน):\n"
                        "   • สีผนังลอก\n"
                        "   • ผนังร้าวเล็กน้อย\n"
                        "   • ฝ้าเพดานมีจุดชื้น\n"
                        "   • เครื่องใช้ไฟฟ้าขัดข้องเล็กน้อย\n"
                        "   • ที่จับประตูหลวม\n\n"
                        
                        "หน้าที่ของคุณ:\n"
                        "1. วิเคราะห์สิ่งที่เห็นในรูปภาพ\n"
                        "2. เปรียบเทียบกับคำอธิบายที่ลูกบ้านแจ้งมา\n"
                        "3. สรุปปัญหาเชิงเทคนิคและคาดการณ์สาเหตุที่เป็นไปได้แม้ลูกบ้านจะไม่ได้แจ้ง\n\n"

                        "Format ตอบ: 'Summary || Urgency || Detailed_Analysis'\n"
                        "- Summary: สรุปปัญหาทางเทคนิคสั้นๆ (ภาษาไทย) ไม่เกิน 100 ตัวอักษร\n"
                        "- Urgency: ประเมินความเร่งด่วน (High, Medium, Low)\n"
                        "- Detailed_Analysis: บทวิเคราะห์เชิงลึกจากภาพและคำอธิบาย (ภาษาไทย) ให้ข้อมูลเพิ่มเติมที่ AI เห็นจากรูปแต่ลูกบ้านอาจไม่ได้แจ้ง เช่น 'จากการตรวจสอบพบว่ามีความเสียหายลึกถึงโครงสร้าง' หรือ 'มีคราบน้ำจากการรั่วซึมมานาน' เป็นต้น\n"
                    )
                    
                    print("🤖 กำลังวิเคราะห์ด้วย gemini-3-flash-preview...")
                    gemini_res = client.models.generate_content(
                        model='gemini-3-flash-preview',
                        contents=[
                            types.Content(
                                role="user",
                                parts=[
                                    types.Part.from_uri(
                                        file_uri=upload_file.uri,
                                        mime_type=upload_file.mime_type
                                    ),
                                    types.Part.from_text(text=vision_prompt)
                                ]
                            )
                        ]
                    )
                    
                    raw_result = gemini_res.text.strip()
                    print(f"🤖 ผลลัพธ์จาก AI Vision: {raw_result}")
                    
                    if "||" in raw_result:
                        parts = raw_result.split("||")
                        if len(parts) >= 3:
                            ai_summary_text = parts[0].strip()
                            ai_urgency = parts[1].strip()
                            detailed_analysis = parts[2].strip()
                            
                            # ผสาน Summary และ Detailed Analysis เพื่อแสดงในระบบ
                            final_ai_summary = f"{ai_summary_text}\n\n🤖 วิเคราะห์เชิงลึก:\n{detailed_analysis}"
                            print(f"🤖 วิเคราะห์ได้: Summary='{ai_summary_text}', Urgency='{ai_urgency}'")
                        elif len(parts) == 2:
                            ai_summary_text = parts[0].strip()
                            ai_urgency = parts[1].strip()
                            final_ai_summary = ai_summary_text
                        else:
                            final_ai_summary = raw_result
                            ai_urgency = "Medium"
                    else:
                        final_ai_summary = raw_result
                        ai_urgency = "Medium"
                        print(f"🤖 ไม่พบรูปแบบที่ถูกต้อง ใช้ค่า default: Urgency='{ai_urgency}'")

                except Exception as e:
                    print(f"❌ Gemini Vision Error: {e}")
                    # ถ้า Error ก็ใช้ข้อความเดิม
                
                # 4. ตัดสินใจขั้นสุดท้าย
                final_urgency = determine_final_urgency(desc_urgency, ai_urgency, user_desc)
                print(f"✅ ความสำคัญขั้นสุดท้าย: {final_urgency}")
                
                # 5. SAVE DB (บันทึกทุกอย่างลง DB)
                new_complaint = {
                    "line_user_id": uid,
                    "room_number": user.get('room_number'),
                    "description": user_desc,
                    "image_url": img_url,
                    "status": "pending",
                    "ai_summary": final_ai_summary,
                    "urgency_level": final_urgency,
                    "timestamp": get_bkk_now(),
                    "priority": final_urgency.lower(),  # แปลงเป็นตัวเล็กเพื่อใช้ใน DB
                    "analysis_debug": {  # เก็บข้อมูล debug สำหรับตรวจสอบ
                        "desc_urgency": desc_urgency,
                        "vision_urgency": ai_urgency,
                        "final_decision": final_urgency,
                        "user_description": user_desc
                    }
                }
                
                complaints_col.insert_one(new_complaint)
                print(f"✅ บันทึกการร้องเรียนสำเร็จ: ID={new_complaint.get('_id')}")
                
                # 6. Clear State
                users_col.update_one(
                    {"line_user_id": uid}, 
                    {"$set": {"complaint_state": "normal", "draft_desc": None}}
                )
                
                # 7. ตอบกลับผู้ใช้ (แก้ไขข้อความ)
                success_msg = (
                    f"✅ รับแจ้งร้องเรียนเรียบร้อยแล้วค่ะ!\n\n"
                    f"📌 เรื่อง: {user_desc}\n"
                    f"📷 ได้รับรูปภาพแล้ว\n"
                    f"เจ้าหน้าที่จะรีบดำเนินการตรวจสอบให้นะคะ ขอบคุณค่ะ 🙏"
                )
                
                line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=success_msg)]))
                
            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()
                line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="เกิดข้อผิดพลาดในการประมวลผลค่ะ โปรดลองอีกครั้ง")]))
            finally:
                if os.path.exists(temp_path): os.remove(temp_path)
        else:
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="ได้รับรูปแล้วค่ะ 📸 (ไม่ได้อยู่ในโหมดแจ้งร้องเรียน)")]))

@line_handler.add(FollowEvent)
def handle_follow(event):
    uid = event.source.user_id
    with ApiClient(line_configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        profile = line_bot_api.get_profile(uid)
        
        user = get_or_create_user(uid, "line", profile.display_name, profile.picture_url)
        
        if is_registered(user):
            msg = (
                f"ยินดีต้อนรับกลับครับ คุณ {user.get('first_name')}! 👋\n"
                f"ข้อมูลปัจจุบันของคุณคือ:\n\n"
                f"🏠 ห้อง: {user.get('room_number')}\n"
                f"👤 ชื่อ: {user.get('first_name')} {user.get('last_name')}\n"
                f"📞 เบอร์: {user.get('phone_number')}\n\n"
                f"หากข้อมูลถูกต้องแล้ว รอรับแจ้งเตือนได้เลยครับ\n"
                f"(หากต้องการเปลี่ยน ให้พิมพ์ 'ลงทะเบียน' ใหม่)"
            )
        else:
            msg = (
                f"สวัสดีคุณ {profile.display_name}! 👋\n\n"
                f"📝 กรุณาลงทะเบียนเพื่อใช้งานแชตบอตนิติบุคคล\n\n"
                f"พิมพ์: ลงทะเบียน [เลขห้อง] [ชื่อ] [นามสกุล] [เบอร์โทร]\n\n"
                f"ตัวอย่าง:\n"
                f"ลงทะเบียน 814 สมชาย ใจดี 0812345678"
            )

        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=msg)]))

# ================= HEALTH CHECK ENDPOINT =================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check MongoDB connection
        mongo_status = mongo_client.server_info() is not None
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.datetime.now().isoformat(),
            "services": {
                "mongodb": mongo_status,
                "cloudinary": True,
                "gemini": True
            }
        })
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

# ================= DASHBOARD ENDPOINT =================

@app.route('/api/dashboard', methods=['GET'])
@require_api_token
def get_dashboard_stats():
    """ดึงข้อมูลสถิติทั้งหมดสำหรับแดชบอร์ด"""
    print(f"DEBUG: Dashboard requested by {request.remote_addr}")
    print(f"DEBUG: Headers: {dict(request.headers)}")
    try:
        # 1. จำนวนผู้ใช้งานทั้งหมด
        total_users = users_col.count_documents({})
        
        # 2. จำนวนร้องเรียนทั้งหมด
        total_complaints = complaints_col.count_documents({})
        
        # 3. ร้องเรียนที่แก้ไขแล้วและยังไม่ได้แก้
        resolved_complaints = complaints_col.count_documents({"status": "resolved"})
        pending_complaints = complaints_col.count_documents({"status": "pending"})
        
        # 4. จำนวนการร้องเรียนแยกตามระดับความสำคัญ
        high_priority = complaints_col.count_documents({"priority": "high", "status": "pending"})
        medium_priority = complaints_col.count_documents({"priority": "medium", "status": "pending"})
        low_priority = complaints_col.count_documents({"priority": "low", "status": "pending"})
        
        # 5. จำนวนพัสดุทั้งหมด
        total_parcels = parcels_col.count_documents({})
        
        # 6. จำนวนพัสดุที่รับแล้ว
        picked_up_parcels = parcels_col.count_documents({"status": "picked_up"})
        
        # 7. จำนวนพัสดุคงค้าง
        pending_parcels = parcels_col.count_documents({"status": "pending"})

        return jsonify({
            "users": total_users,
            "total_complaints": total_complaints,
            "resolved_complaints": resolved_complaints,
            "pending_complaints": pending_complaints,
            "pending_high": high_priority,
            "pending_medium": medium_priority,
            "pending_low": low_priority,
            "total_parcels": total_parcels,
            "picked_up_parcels": picked_up_parcels,
            "pending_parcels": pending_parcels
        })
    except Exception as e:
        print(f"Error dashboard: {e}")
        return jsonify({"error": str(e)}), 500

# ================= ACTIVITY ENDPOINT =================

@app.route('/api/activity', methods=['GET'])
@require_api_token
def get_recent_activity():
    """ดึงกิจกรรมล่าสุด"""
    try:
        # ดึงกิจกรรมจาก parcels และ complaints
        recent_parcels = list(parcels_col.find().sort("timestamp", -1).limit(3))
        recent_complaints = list(complaints_col.find().sort("timestamp", -1).limit(3))
        
        activities = []
        
        for parcel in recent_parcels:
            activities.append({
                "type": "parcel",
                "message": f"พัสดุใหม่: ห้อง {parcel.get('room_number', '-')}",
                "details": f"{parcel.get('transport', '-')} - {parcel.get('recipient_name', '-')}",
                "timestamp": parcel.get('timestamp').strftime("%Y-%m-%d %H:%M") if parcel.get('timestamp') else "-"
            })
        
        for complaint in recent_complaints:
            user = users_col.find_one({"line_user_id": complaint.get("line_user_id")})
            activities.append({
                "type": "complaint",
                "message": f"แจ้งร้องเรียน: ห้อง {complaint.get('room_number', '-')}",
                "details": f"{complaint.get('description', '-')[:30]}...",
                "timestamp": complaint.get('timestamp').strftime("%Y-%m-%d %H:%M") if complaint.get('timestamp') else "-"
            })
        
        # เรียงตามเวลา
        activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return jsonify({"activities": activities[:5]})
    except Exception as e:
        print(f"Activity Error: {e}")
        return jsonify({"activities": []})

# ================= UPCOMING PARCELS ENDPOINT =================

@app.route('/api/upcoming-parcels', methods=['GET'])
@require_api_token
def get_upcoming_parcels():
    """ดึงพัสดุที่เร็วสุดถึงกำหนด"""
    try:
        # ดึงพัสดุที่ pending และเก่าที่สุด
        upcoming = list(parcels_col.find({"status": "pending"})
                       .sort("timestamp", 1)  # เก่าที่สุดก่อน
                       .limit(5))
        
        result = []
        for parcel in upcoming:
            result.append({
                "room_number": parcel.get("room_number", "-"),
                "recipient_name": parcel.get("recipient_name", "-"),
                "transport": parcel.get("transport", "-"),
                "timestamp": parcel.get('timestamp').strftime("%Y-%m-%d %H:%M") if parcel.get('timestamp') else "-"
            })
        
        return jsonify({"parcels": result})
    except Exception as e:
        print(f"Upcoming Parcels Error: {e}")
        return jsonify({"parcels": []})

# ================= USERS ENDPOINT =================

@app.route('/api/users', methods=['GET'])
@require_api_token
def get_all_users():
    """ดึงข้อมูลผู้ใช้ทั้งหมด"""
    try:
        print(f"DEBUG: Users requested by {request.remote_addr}")
        users = list(users_col.find().sort("last_active", -1).limit(100))
        print(f"DEBUG: Found {len(users)} users in DB")
        
        result = []
        for u in users:
            # Helper function เพื่อจัดการค่า null
            def get_value(key, default="-"):
                value = u.get(key)
                if value is None:
                    return default
                return str(value) if value else default
            
            # Format ชื่อ-นามสกุล
            first_name = get_value('first_name', '')
            last_name = get_value('last_name', '')
            full_name = f"{first_name} {last_name}".strip()
            
            if not full_name or full_name == " ":
                full_name = get_value('display_name', '-')
            
            # ตรวจสอบ Platform
            platform = "LINE" if u.get("line_user_id") else "Web/App"
            
            # Format เวลาใช้งานล่าสุด
            last_active = u.get("last_active")
            if isinstance(last_active, datetime.datetime):
                last_active_str = last_active.strftime("%Y-%m-%d %H:%M")
            elif last_active:
                last_active_str = str(last_active)
            else:
                last_active_str = "-"
            
            # เตรียมข้อมูลสำหรับ response
            user_data = {
                "room_number": get_value('room_number'),
                "name": full_name,
                "display_name": get_value('display_name'),
                "phone_number": get_value('phone_number'),
                "platform": platform,
                "last_active": last_active_str
            }
            
            print(f"User data: {user_data}")  # สำหรับ debug
            result.append(user_data)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error getting users: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= 5. แก้ไขฟังก์ชัน get_all_complaints =================

@app.route('/api/complaints', methods=['GET'])
@require_api_token
def get_all_complaints():
    try:
        # Parameters
        status_filter = request.args.get('status', 'pending')
        sort_by = request.args.get('sort', 'priority:desc')  # priority:desc, time:desc, time:asc
        search_q = request.args.get('q', '').strip()
        
        # Build Query
        query = {}
        if status_filter != 'all':
            query['status'] = status_filter
            
        if search_q:
            query["$or"] = [
                {"room_number": {"$regex": search_q, "$options": "i"}},
                {"description": {"$regex": search_q, "$options": "i"}},
                {"ai_summary": {"$regex": search_q, "$options": "i"}}
            ]
            
        items = list(complaints_col.find(query))
        
        # 🔥 ปรับปรุง Sorting Logic ใหม่
        def get_priority_score(priority):
            priority_map = {
                'high': 100,
                'medium': 50,
                'low': 10
            }
            return priority_map.get(priority.lower(), 0)
        
        # เรียงลำดับตามความสำคัญ (สูงสุดก่อน) และตามเวลา (ใหม่ก่อน)
        if sort_by == 'priority:desc':
            items.sort(key=lambda x: (
                -get_priority_score(x.get('priority', 'medium')),  # ความสำคัญ (สูงมาก่อน)
                -(x.get('timestamp', datetime.datetime.min).timestamp())  # ใหม่ก่อน
            ))
        elif sort_by == 'time:asc':
            items.sort(key=lambda x: x.get('timestamp', datetime.datetime.min))
        elif sort_by == 'time:desc':
            items.sort(key=lambda x: x.get('timestamp', datetime.datetime.min), reverse=True)
        else: # default priority
            items.sort(key=lambda x: (
                -get_priority_score(x.get('priority', 'medium')),
                -(x.get('timestamp', datetime.datetime.min).timestamp())
            ))

        result = []
        for c in items:
            # หาข้อมูลผู้ใช้เพิ่มเติม
            user = users_col.find_one({"line_user_id": c.get("line_user_id")})
            
            # แปลง priority เป็นภาษาไทยสำหรับแสดงผล
            priority_th = {
                "high": "สูง (ต้องแก้ไขวันนี้)",
                "medium": "กลาง (แก้ไข 1-2 วัน)",
                "low": "ต่ำ (แก้ไข 3-5 วัน)"
            }.get(c.get("priority", "medium"), c.get("priority", "medium"))
            
            result.append({
                "id": str(c.get('_id')),
                "room_number": c.get("room_number", "-"),
                "description": c.get("description", "-"),
                "summary": c.get("ai_summary", "-"),
                "status": c.get("status", "pending"),
                "priority": c.get("priority", "medium"),
                "priority_th": priority_th,
                "timestamp": c.get("timestamp", "").strftime("%Y-%m-%d %H:%M:%S") if c.get("timestamp") else "-",
                "image_url": c.get("image_url", ""),
                "display_name": user.get("display_name", "-") if user else "-",
                "first_name": user.get("first_name", "") if user else "",
                "last_name": user.get("last_name", "") if user else "",
                "urgency_level": c.get("urgency_level", "Medium")
            })
        return jsonify({"items": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= PARCELS ENDPOINT =================

@app.route('/api/parcels', methods=['GET'])
@require_api_token
def get_parcels_frontend():
    try:
        q = request.args.get('q', '').strip()
        query = {"status": "pending"}
        
        if q:
            query["$or"] = [
                {"room_number": {"$regex": q, "$options": "i"}},
                {"recipient_name": {"$regex": q, "$options": "i"}},
                {"pin": q},
                {"tracking_number": {"$regex": q, "$options": "i"}},
                {"transport": {"$regex": q, "$options": "i"}}
            ]
            
        items = list(parcels_col.find(query).sort("timestamp", -1).limit(1000))
        result = []
        for i in items:
            result.append({
                "id": str(i['_id']),
                "room_number": i.get("room_number", "-"),
                "recipient_name": i.get("recipient_name", "-"),
                "pin": i.get("pin", "-"),
                "courier": i.get("transport", "-"),
                "tracking_number": i.get("tracking_number", "-"),
                "image_url": i.get("image_url", "")
            })
        return jsonify({"items": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= USERS SEARCH ENDPOINT =================

@app.route('/api/users/search', methods=['GET'])
@require_api_token
def search_users():
    """ค้นหาผู้ใช้แบบ real-time"""
    try:
        query = request.args.get('q', '').strip()
        
        if not query or len(query) < 1:  # ถ้าไม่มีคำค้นหาหรือน้อยกว่า 1 ตัวอักษร
            users = list(users_col.find().sort("last_active", -1).limit(50))
        else:
            # สร้าง regex สำหรับค้นหาแบบ case-insensitive
            regex_pattern = f".*{query}.*"
            
            # ค้นหาจากหลายฟิลด์
            search_query = {
                "$or": [
                    {"room_number": {"$regex": query, "$options": "i"}},
                    {"first_name": {"$regex": query, "$options": "i"}},
                    {"last_name": {"$regex": query, "$options": "i"}},
                    {"display_name": {"$regex": query, "$options": "i"}},
                    {"phone_number": {"$regex": query, "$options": "i"}}
                ]
            }
            
            users = list(users_col.find(search_query).sort("last_active", -1).limit(50))
        
        result = []
        for u in users:
            # Helper function เพื่อจัดการค่า null
            def get_value(key, default="-"):
                value = u.get(key)
                if value is None:
                    return default
                return str(value) if value else default
            
            # Format ชื่อ-นามสกุล
            first_name = get_value('first_name', '')
            last_name = get_value('last_name', '')
            full_name = f"{first_name} {last_name}".strip()
            
            if not full_name or full_name == " ":
                full_name = get_value('display_name', '-')
            
            # ตรวจสอบ Platform - อ่านจากฐานข้อมูลโดยตรง
            platform = u.get("platform", "")
            if not platform:
                # Fallback: ถ้าไม่มี platform ให้ดูจาก line_user_id
                platform = "LINE" if u.get("line_user_id") else "Web"
            
            # Format เวลาใช้งานล่าสุด
            last_active = u.get("last_active")
            if isinstance(last_active, datetime.datetime):
                last_active_str = last_active.strftime("%Y-%m-%d %H:%M")
            elif last_active:
                last_active_str = str(last_active)
            else:
                last_active_str = "-"
            
            # เตรียมข้อมูลสำหรับ response
            user_data = {
                "room_number": get_value('room_number'),
                "name": full_name,
                "display_name": get_value('display_name'),
                "phone_number": get_value('phone_number'),
                "platform": platform,
                "last_active": last_active_str
            }
            
            result.append(user_data)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error searching users: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= PARCELS SEARCH ENDPOINT (OPTIMIZED) =================

@app.route('/api/parcels/search', methods=['GET'])
@require_api_token
def search_parcels_optimized():
    """ค้นหาพัสดุแบบ real-time (optimized)"""
    try:
        q = request.args.get('q', '').strip()
        query = {"status": "pending"}
        
        if q and len(q) >= 1:  # ถ้ามีคำค้นหาและยาวอย่างน้อย 1 ตัวอักษร
            # ตรวจสอบว่าเป็น PIN (ตัวเลข 5 หลัก) หรือไม่
            if q.isdigit() and len(q) == 5:
                query["pin"] = q
            else:
                # ค้นหาแบบ regex จากหลายฟิลด์
                query["$or"] = [
                    {"room_number": {"$regex": q, "$options": "i"}},
                    {"recipient_name": {"$regex": q, "$options": "i"}},
                    {"tracking_number": {"$regex": q, "$options": "i"}},
                    {"transport": {"$regex": q, "$options": "i"}}
                ]
        
        # ใช้ projection เพื่อเลือกเฉพาะฟิลด์ที่จำเป็น
        items = list(parcels_col.find(query, {
            "room_number": 1,
            "recipient_name": 1,
            "pin": 1,
            "transport": 1,
            "tracking_number": 1,
            "image_url": 1,
            "timestamp": 1,
            "_id": 1
        }).sort("timestamp", -1).limit(100))
        
        result = []
        for i in items:
            result.append({
                "id": str(i['_id']),
                "room_number": i.get("room_number", "-"),
                "recipient_name": i.get("recipient_name", "-"),
                "pin": i.get("pin", "-"),
                "courier": i.get("transport", "-"),
                "tracking_number": i.get("tracking_number", "-"),
                "image_url": i.get("image_url", ""),
                "timestamp": i.get('timestamp').strftime("%Y-%m-%d %H:%M") if i.get('timestamp') else "-"
            })
        
        return jsonify({"items": result})
    except Exception as e:
        print(f"Parcels search error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= COMPLAINTS SEARCH ENDPOINT (OPTIMIZED) =================

@app.route('/api/complaints/search', methods=['GET'])
@require_api_token
def search_complaints_optimized():
    """ค้นหาร้องเรียนแบบ real-time (optimized)"""
    try:
        search_q = request.args.get('q', '').strip()
        status_filter = request.args.get('status', 'pending')
        
        # Build Query
        query = {}
        if status_filter != 'all':
            query['status'] = status_filter
            
        if search_q and len(search_q) >= 1:
            # ค้นหาจากหลายฟิลด์
            query["$or"] = [
                {"room_number": {"$regex": search_q, "$options": "i"}},
                {"description": {"$regex": search_q, "$options": "i"}},
                {"ai_summary": {"$regex": search_q, "$options": "i"}},
                {"priority": {"$regex": search_q, "$options": "i"}}
            ]
            
        # ใช้ projection เพื่อเลือกเฉพาะฟิลด์ที่จำเป็น
        items = list(complaints_col.find(query, {
            "room_number": 1,
            "description": 1,
            "ai_summary": 1,
            "status": 1,
            "priority": 1,
            "timestamp": 1,
            "image_url": 1,
            "line_user_id": 1,
            "urgency_level": 1,
            "_id": 1
        }))
        
        # เรียงลำดับตามความสำคัญ (สูงสุดก่อน) และตามเวลา (ใหม่ก่อน)
        def get_priority_score(priority):
            priority_map = {
                'high': 100,
                'medium': 50,
                'low': 10
            }
            return priority_map.get(priority.lower(), 0)
        
        items.sort(key=lambda x: (
            -get_priority_score(x.get('priority', 'medium')),
            -(x.get('timestamp', datetime.datetime.min).timestamp())
        ))

        result = []
        for c in items:
            # หาข้อมูลผู้ใช้เพิ่มเติม
            user = users_col.find_one({"line_user_id": c.get("line_user_id")})
            
            result.append({
                "id": str(c.get('_id')),
                "room_number": c.get("room_number", "-"),
                "description": c.get("description", "-"),
                "summary": c.get("ai_summary", "-"),
                "status": c.get("status", "pending"),
                "priority": c.get("priority", "medium"),
                "timestamp": c.get("timestamp", "").strftime("%Y-%m-%d %H:%M:%S") if c.get("timestamp") else "-",
                "image_url": c.get("image_url", ""),
                "display_name": user.get("display_name", "-") if user else "-",
                "urgency_level": c.get("urgency_level", "Medium")
            })
        return jsonify({"items": result})
    except Exception as e:
        print(f"Complaints search error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= SCAN PARCEL API (ENHANCED) =================

@app.route('/api/scan', methods=['POST'])
@require_api_token
def scan_parcel_api():
    # API สำหรับ Frontend Upload ภาพพัสดุ -> ให้ Gemini อ่าน
    if 'image' not in request.files:
        return jsonify({"status": "error", "message": "No image uploaded"}), 400

    file = request.files['image']
    
    # [NEW] Validate Image
    is_valid, error_msg = validate_image(file)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 400

    suffix = f".{file.filename.rsplit('.', 1)[1].lower()}" if '.' in file.filename else '.jpg'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
        file.save(tf.name)
        temp_path = tf.name

    try:
        # 1. Upload Cloudinary ด้วย upload preset (90 วัน)
        up_res = cloudinary.uploader.upload(
            temp_path,
            folder="parcels",
            tags=["parcel", "temporary"]
        )
        img_url = up_res.get('secure_url')

        # 2. Upload to Gemini for processing
        upload_file = client.files.upload(file=temp_path)
        while upload_file.state.name == "PROCESSING":
            time.sleep(1)
            upload_file = client.files.get(name=upload_file.name)

        # 3. Prompt Gemini to extract fields in JSON (ENHANCED)
        prompt = """
        Analyze this parcel label image. Extract the following information into a JSON object:
        - "room_number": Identify the room or unit number (e.g., "814", "1205/1"). If not clearly visible, return "-".
        - "recipient_name": Extract the full name of the recipient in Thai or English. If not found, return "-".
        - "courier": Identify the transport/delivery company from their logo or text (e.g., "Kerry", "Flash", "J&T", "Post", "Ninjavan"). If not found, return "-".
        - "tracking_number": Extract the tracking number or barcode value. If not found, return "-".
        
        Guidelines:
        - Return ONLY the JSON object.
        - Do NOT include markdown code blocks (no ```json).
        - Use Thai for names if visible in Thai.
        """
        
        gemini_res = client.models.generate_content(
            model='gemini-3-flash-preview', # Use fast model for OCR
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(file_uri=upload_file.uri, mime_type=upload_file.mime_type),
                        types.Part.from_text(text=prompt)
                    ]
                )
            ]
        )
        
        raw_text = gemini_res.text.strip().replace("```json", "").replace("```", "")
        data = json.loads(raw_text)
        
        # 4. ENHANCED USER MATCHING - ค้นหาผู้ใช้จากฐานข้อมูล
        room_number = data.get("room_number", "-")
        recipient_name = data.get("recipient_name", "-")
        
        # ค้นหาผู้ใช้จากห้อง
        user_found = find_user_by_room_or_name(
            room_number=room_number,
            recipient_name=recipient_name
        )
        
        # ค้นหาผู้ใช้จากชื่อแบบ fuzzy match
        fuzzy_matches = []
        if recipient_name != "-":
            fuzzy_matches = find_users_by_name_fuzzy(recipient_name)
        
        # 5. Count existing parcels if room is found
        parcel_count = 0
        if room_number and room_number != "-":
             parcel_count = parcels_col.count_documents({"room_number": room_number, "status": "pending"})

        return jsonify({
            "status": "success",
            "data": {
                "room_number": room_number,
                "recipient_name": recipient_name,
                "transport": data.get("courier", "-"),
                "tracking_number": data.get("tracking_number", "-"),
                "image_url": img_url,
                "parcel_count": parcel_count,
                "user_found": {
                    "exists": user_found is not None,
                    "line_user_id": user_found.get("line_user_id") if user_found else None,
                    "display_name": user_found.get("display_name") if user_found else None,
                    "room_number": user_found.get("room_number") if user_found else None,
                    "first_name": user_found.get("first_name") if user_found else None,
                    "last_name": user_found.get("last_name") if user_found else None
                } if user_found else None,
                "fuzzy_matches": [
                    {
                        "display_name": u.get("display_name"),
                        "first_name": u.get("first_name"),
                        "last_name": u.get("last_name"),
                        "room_number": u.get("room_number"),
                        "phone_number": u.get("phone_number")
                    } for u in fuzzy_matches[:3]  # แสดงเฉพาะ 3 รายการแรก
                ]
            }
        })

    except Exception as e:
        print(f"Scan API Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

# ================= CONFIRM PARCEL AND NOTIFY (MODIFIED) =================

@app.route('/api/confirm', methods=['POST'])
@require_api_token
def confirm_parcel_and_notify():
    """ยืนยันพัสดุและส่ง LINE แจ้งเตือน - MODIFIED: ไม่บันทึกถ้าไม่พบผู้ใช้"""
    try:
        data = request.json
        # ✅ แก้ไข: Decode ชื่อแอดมินจาก Header
        admin_name_header = request.headers.get('X-Admin-Name', 'Unknown Admin')
        admin_name = urllib.parse.unquote(admin_name_header)
        
        # ตรวจสอบข้อมูล
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400
        
        # 1. ค้นหาผู้ใช้จากห้องหรือชื่อ (ใช้ฟังก์ชันที่แก้ไขแล้ว)
        user = find_user_by_room_or_name(
            room_number=data.get("room_number"),
            recipient_name=data.get("recipient_name")
        )
        
        # 2. ถ้าไม่พบผู้ใช้ ให้คืน error และไม่บันทึกข้อมูล
        if not user:
            return jsonify({
                "status": "error", 
                "message": "ไม่พบเจ้าของห้องในระบบ กรุณาตรวจสอบข้อมูลหรือลงทะเบียนผู้ใช้ก่อน",
                "notification_lines": [
                    "❌ ไม่สามารถบันทึกพัสดุได้",
                    f"   ห้องที่ค้นหา: {data.get('room_number', '-')}",
                    f"   ชื่อที่ค้นหา: {data.get('recipient_name', '-')}",
                    "   กรุณาตรวจสอบข้อมูลหรือให้ผู้ใช้ลงทะเบียนก่อน"
                ]
            }), 400
        
        # 3. ถ้าพบผู้ใช้ ให้ดำเนินการต่อ
        # สร้าง PIN 5 หลักแบบสุ่ม
        pin = str(random.randint(10000, 99999))
        
        # 4. สร้างพัสดุใหม่
        new_parcel = {
            "room_number": data.get("room_number", "-"),
            "recipient_name": data.get("recipient_name", "-"),
            "transport": data.get("transport", data.get("courier", "-")), # ✅ รองรับทั้ง transport และ courier
            "tracking_number": data.get("tracking_number", "-"),
            "pin": pin,
            "image_url": data.get("image_url", ""),
            "status": "pending",
            "timestamp": datetime.datetime.now()
        }
        
        parcels_col.insert_one(new_parcel)
        
        # 5. บันทึก Audit Log (เปลี่ยนชื่อเป็น "สแกนเข้าระบบ")
        log_admin_action(
            action="สแกนเข้าระบบ",
            performed_by=admin_name,
            target=f"Room: {data.get('room_number', '-')}, Recipient: {data.get('recipient_name', '-')}",
            details=f"PIN: {pin}, Courier: {data.get('transport', data.get('courier', '-'))}, Tracking: {data.get('tracking_number', '-')}"
        )
        
        # 6. ส่ง LINE แจ้งเตือน
        notification_sent = False
        notification_lines = []
        
        # สร้างข้อความแจ้งเตือน
        message = (
            f"📦 คุณมีพัสดุใหม่!\n\n"
            f"🏠 ห้อง: {data.get('room_number', '-')}\n"
            f"👤 ผู้รับ: {data.get('recipient_name', '-')}\n"
            f"🚚 ขนส่ง: {data.get('transport', data.get('courier', '-'))}\n"
            f"🔢 เลขติดตาม: {data.get('tracking_number', '-')}\n"
            f"🔑 PIN: {pin}\n\n"
            f"กรุณานำ PIN นี้ไปรับพัสดุที่สำนักงานค่ะ"
        )
        
        # ส่งรูปภาพพัสดุด้วยถ้ามี
        image_url = data.get("image_url")
        
        try:
            if send_line_message(user["line_user_id"], message, image_url):
                notification_sent = True
                notification_lines.append(f"✅ ส่งแจ้งเตือนถึง: {user.get('display_name', 'Unknown')} (ห้อง {user.get('room_number', '-')})")
                print(f"✅ LINE notification sent to {user['line_user_id']}")
            else:
                notification_lines.append("⚠️ ไม่สามารถส่งแจ้งเตือน LINE ได้")
                print(f"❌ Failed to send LINE notification")
        except Exception as e:
            notification_lines.append(f"⚠️ LINE sending error: {str(e)}")
            print(f"❌ LINE sending error: {e}")
        
        # 7. นับพัสดุคงค้างใหม่
        parcel_count = 0
        room = data.get("room_number")
        if room and room != "-":
            parcel_count = parcels_col.count_documents({"room_number": room, "status": "pending"})
        
        return jsonify({
            "status": "saved",
            "message": "บันทึกพัสดุสำเร็จ",
            "pin": pin,
            "parcel_count": parcel_count,
            "sent": notification_sent,
            "notification_lines": notification_lines,
            "user_found": True
        })
        
    except Exception as e:
        print(f"❌ Confirm Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= PICKUP PARCEL =================

@app.route('/api/pickup', methods=['POST'])
@require_api_token
def pickup_parcel():
    """รับพัสดุและส่ง LINE แจ้งเตือนการรับ"""
    try:
        data = request.json
        pin = data.get("pin")
        # ✅ แก้ไข: Decode ชื่อแอดมินจาก Header
        admin_name_header = request.headers.get('X-Admin-Name', 'Unknown Admin')
        admin_name = urllib.parse.unquote(admin_name_header)
        
        if not pin:
            return jsonify({"status": "error", "message": "PIN is required"}), 400
        
        # 1. ค้นหาพัสดุด้วย PIN
        parcel = parcels_col.find_one({"pin": str(pin).strip(), "status": "pending"})
        
        if not parcel:
            return jsonify({"status": "error", "message": "ไม่พบพัสดุหรือรับไปแล้ว"}), 404
        
        # 2. อัพเดตสถานะเป็น picked_up
        parcels_col.update_one(
            {"_id": parcel["_id"]},
            {"$set": {"status": "picked_up", "pickup_time": datetime.datetime.now()}}
        )
        
        # 3. บันทึก Audit Log (เปลี่ยนชื่อให้ตรงกับความต้องการของ user)
        log_admin_action(
            action="กดรับของ",
            performed_by=admin_name,
            target=f"Room: {parcel.get('room_number', '-')}, PIN: {pin}",
            details=f"Tracking: {parcel.get('tracking_number', '-')}, Courier: {parcel.get('transport', '-')}"
        )
        
        # 4. ค้นหาผู้ใช้จากห้อง
        user = users_col.find_one({"room_number": parcel.get("room_number")})
        
        # 5. ส่ง LINE แจ้งเตือนการรับพัสดุ
        if user and user.get("line_user_id"):
            message = (
                f"✅ พัสดุของคุณถูกรับแล้ว!\n\n"
                f"📦 พัสดุ: {parcel.get('tracking_number', '-')}\n"
                f"🏠 ห้อง: {parcel.get('room_number', '-')}\n"
                f"🚚 ขนส่ง: {parcel.get('transport', '-')}\n"
                f"🔑 PIN: {parcel.get('pin', '-')}\n"
                f"⏰ เวลารับ: {datetime.datetime.now().strftime('%H:%M %d/%m/%Y')}\n\n"
                f"ขอบคุณที่ใช้บริการค่ะ"
            )
            
            # ส่งรูปภาพพัสดุด้วยถ้ามี
            image_url = parcel.get("image_url")
            
            send_line_message(user["line_user_id"], message, image_url)
            print(f"✅ Pickup notification sent to {user['line_user_id']}")
        
        return jsonify({
            "status": "success",
            "message": "บันทึกรับพัสดุสำเร็จ",
            "parcel": {
                "room_number": parcel.get("room_number"),
                "tracking_number": parcel.get("tracking_number"),
                "transport": parcel.get("transport"),
                "pin": parcel.get("pin")
            }
        })
        
    except Exception as e:
        print(f"❌ Pickup Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= RESOLVE COMPLAINT (แก้ไขข้อความ) =================

@app.route('/api/complaints/<complaint_id>/resolve', methods=['POST'])
@require_api_token
def resolve_complaint(complaint_id):
    """ปิดงานร้องเรียนและส่ง LINE แจ้งเตือน"""
    try:
        # ✅ แก้ไข: Decode ชื่อแอดมินจาก Header
        admin_name_header = request.headers.get('X-Admin-Name', 'Unknown Admin')
        admin_name = urllib.parse.unquote(admin_name_header)
        
        # 1. ตรวจสอบ complaint_id
        try:
            obj_id = ObjectId(complaint_id)
        except:
            return jsonify({"status": "error", "message": "Invalid complaint ID"}), 400
        
        # 2. ค้นหารายการร้องเรียน
        complaint = complaints_col.find_one({"_id": obj_id})
        
        if not complaint:
            return jsonify({"status": "error", "message": "Complaint not found"}), 404
        
        # 3. อัพเดตสถานะ
        resolved_note = request.form.get("note", "")
        complaints_col.update_one(
            {"_id": obj_id},
            {"$set": {
                "status": "resolved",
                "resolved_at": datetime.datetime.now(),
                "resolved_by": admin_name,
                "resolved_note": resolved_note
            }}
        )
        
        # 4. บันทึก Audit Log
        log_admin_action(
            action="Resolve Complaint",
            performed_by=admin_name,
            target=f"Complaint ID: {complaint_id}, Room: {complaint.get('room_number', '-')}",
            details=f"Description: {complaint.get('description', '')[:50]}..., Note: {resolved_note}"
        )
        
        # 5. ถ้ามีรูปภาพให้อัพโหลด (ใช้ upload preset)
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                # [NEW] Validate Image
                is_valid, error_msg = validate_image(file)
                if not is_valid:
                    return jsonify({"status": "error", "message": error_msg}), 400
                
                suffix = f".{file.filename.rsplit('.', 1)[1].lower()}" if '.' in file.filename else '.jpg'
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
                    file.save(tf.name)
                    temp_path = tf.name
                
                try:
                    up_res = cloudinary.uploader.upload(
                        temp_path,
                        folder="complaints_resolved",
                        tags=["complaint_resolved", f"complaint:{complaint_id}"]
                    )
                    image_url = up_res.get('secure_url')
                    
                    # บันทึก URL รูปภาพลงใน complaint
                    complaints_col.update_one(
                        {"_id": obj_id},
                        {"$set": {"resolved_image_url": image_url}}
                    )
                except Exception as e:
                    print(f"Image upload error: {e}")
                finally:
                    if os.path.exists(temp_path): os.remove(temp_path)
        
        # 6. ส่ง LINE แจ้งเตือนไปยังผู้ใช้ (แก้ไขข้อความ)
        user = users_col.find_one({"line_user_id": complaint.get("line_user_id")})
        
        if user:
            message = (
                f"✅ การร้องเรียนของคุณได้รับการแก้ไขแล้ว!\n\n"
                f"📌 เรื่อง: {complaint.get('description', '')}\n"
                f"🏠 ห้อง: {complaint.get('room_number', '-')}\n"
                f"📅 วันที่แจ้ง: {complaint.get('timestamp', '').strftime('%d/%m/%Y') if complaint.get('timestamp') else '-'}\n"
                f"✅ ดำเนินการเสร็จ: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
            )
            
            if resolved_note:
                message += f"\n📝 หมายเหตุ: {resolved_note}"
            
            message += "\n\nขอบคุณที่แจ้งปัญหาค่ะ 🙏"
            
            # ส่งรูปภาพแก้ไขด้วยถ้ามี
            send_line_message(user["line_user_id"], message, image_url)
        
        return jsonify({
            "status": "success",
            "message": "Complaint resolved successfully"
        })
        
    except Exception as e:
        print(f"Resolve Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= AUDIT LOGS ENDPOINT =================

@app.route('/api/admin/audit-logs', methods=['GET'])
@require_api_token
def get_audit_logs():
    """ดึง Audit Logs ล่าสุด"""
    try:
        # ดึง logs ล่าสุด 30 รายการ (เรียงจากใหม่ไปเก่า) ตามคำขอของ user
        logs = list(audit_logs_col.find().sort("timestamp", -1).limit(30))
        
        result = []
        for log in logs:
            result.append({
                "action": log.get("action", ""),
                "performed_by": log.get("performed_by", ""),
                "target": log.get("target", ""),
                "timestamp": log.get("timestamp", "").strftime("%Y-%m-%d %H:%M:%S") if log.get("timestamp") else "",
                "details": log.get("details", "")
            })
        
        return jsonify({"logs": result})
    except Exception as e:
        print(f"Audit Logs Error: {e}")
        return jsonify({"error": str(e)}), 500

# ================= EXPORT DATA ENDPOINTS =================

@app.route('/api/admin/export/complaints', methods=['GET'])
@require_api_token
def export_complaints():
    """Export complaints data to CSV"""
    try:
        # ดึงข้อมูล complaints ทั้งหมด
        complaints = list(complaints_col.find())
        
        # สร้าง CSV ใน memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # เขียน header
        writer.writerow([
            'ID', 'ห้อง', 'คำอธิบาย', 'สรุปจาก AI', 'สถานะ', 
            'ความสำคัญ', 'ระดับความเร่งด่วน', 'วันที่แจ้ง', 'วันที่แก้ไข',
            'LINE User ID', 'รูปภาพ URL', 'หมายเหตุการแก้ไข'
        ])
        
        # เขียนข้อมูล
        for comp in complaints:
            writer.writerow([
                str(comp.get('_id', '')),
                comp.get('room_number', ''),
                comp.get('description', ''),
                comp.get('ai_summary', ''),
                comp.get('status', ''),
                comp.get('priority', ''),
                comp.get('urgency_level', ''),
                comp.get('timestamp', '').strftime('%Y-%m-%d %H:%M:%S') if comp.get('timestamp') else '',
                comp.get('resolved_at', '').strftime('%Y-%m-%d %H:%M:%S') if comp.get('resolved_at') else '',
                comp.get('line_user_id', ''),
                comp.get('image_url', ''),
                comp.get('resolved_note', '')
            ])
        
        # สร้าง response
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=complaints_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )
        
    except Exception as e:
        print(f"Export Complaints Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/export/parcels', methods=['GET'])
@require_api_token
def export_parcels():
    """Export parcels data to CSV"""
    try:
        # ดึงข้อมูล parcels ทั้งหมด
        parcels = list(parcels_col.find())
        
        # สร้าง CSV ใน memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # เขียน header
        writer.writerow([
            'ID', 'ห้อง', 'ชื่อผู้รับ', 'บริษัทขนส่ง', 'เลขพัสดุ',
            'PIN', 'สถานะ', 'วันที่รับเข้า', 'วันที่รับออก', 
            'รูปภาพ URL', 'หมายเหตุ'
        ])
        
        # เขียนข้อมูล
        for parcel in parcels:
            writer.writerow([
                str(parcel.get('_id', '')),
                parcel.get('room_number', ''),
                parcel.get('recipient_name', ''),
                parcel.get('transport', ''),
                parcel.get('tracking_number', ''),
                parcel.get('pin', ''),
                parcel.get('status', ''),
                parcel.get('timestamp', '').strftime('%Y-%m-%d %H:%M:%S') if parcel.get('timestamp') else '',
                parcel.get('pickup_time', '').strftime('%Y-%m-%d %H:%M:%S') if parcel.get('pickup_time') else '',
                parcel.get('image_url', ''),
                ''
            ])
        
        # สร้าง response
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=parcels_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )
        
    except Exception as e:
        print(f"Export Parcels Error: {e}")
        return jsonify({"error": str(e)}), 500

# ================= CLOUDINARY AUTO-DELETE HELPER =================

def cleanup_old_cloudinary_images():
    """
    ลบรูปภาพใน Cloudinary ที่เก่ากว่า 90 วัน
    ควรเรียกใช้งานเป็น scheduled task (cron job)
    """
    try:
        # คำนวณวันที่ 90 วันก่อน
        ninety_days_ago = datetime.datetime.now() - datetime.timedelta(days=90)
        
        # 1. ลบรูปภาพพัสดุที่เก่า
        old_parcels = list(parcels_col.find({
            "timestamp": {"$lt": ninety_days_ago},
            "image_url": {"$ne": None, "$ne": ""}
        }))
        
        for parcel in old_parcels:
            try:
                # ดึง public_id จาก URL
                image_url = parcel.get("image_url")
                if image_url and "cloudinary.com" in image_url:
                    # ดึง public_id จาก URL
                    # Format: https://res.cloudinary.com/cloudname/image/upload/v1234567890/folder/filename.jpg
                    parts = image_url.split("/")
                    if len(parts) > 0:
                        filename = parts[-1].split(".")[0]
                        folder = parts[-2] if len(parts) > 1 else ""
                        public_id = f"{folder}/{filename}" if folder else filename
                        
                        # ลบรูปจาก Cloudinary
                        cloudinary.uploader.destroy(public_id)
                        print(f"🗑️ Deleted old parcel image: {public_id}")
            except Exception as e:
                print(f"Error deleting parcel image: {e}")
        
        # 2. ลบรูปภาพร้องเรียนที่เก่า
        old_complaints = list(complaints_col.find({
            "timestamp": {"$lt": ninety_days_ago},
            "image_url": {"$ne": None, "$ne": ""}
        }))
        
        for complaint in old_complaints:
            try:
                image_url = complaint.get("image_url")
                if image_url and "cloudinary.com" in image_url:
                    parts = image_url.split("/")
                    if len(parts) > 0:
                        filename = parts[-1].split(".")[0]
                        folder = parts[-2] if len(parts) > 1 else ""
                        public_id = f"{folder}/{filename}" if folder else filename
                        
                        cloudinary.uploader.destroy(public_id)
                        print(f"🗑️ Deleted old complaint image: {public_id}")
            except Exception as e:
                print(f"Error deleting complaint image: {e}")
                
        return True
    except Exception as e:
        print(f"Cloudinary cleanup error: {e}")
        return False

# API สำหรับเรียกใช้งาน cleanup (ควรเรียกจาก cron job)
@app.route('/api/admin/cleanup-images', methods=['POST'])
@require_api_token
def api_cleanup_images():
    """API สำหรับลบรูปภาพเก่าใน Cloudinary"""
    try:
        result = cleanup_old_cloudinary_images()
        if result:
            return jsonify({"status": "success", "message": "Cleanup completed"})
        else:
            return jsonify({"status": "error", "message": "Cleanup failed"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= WEB CHAT API (แก้ไขให้รองรับการแจ้งร้องเรียนพร้อมรูปภาพ) =================

@app.route('/api/web/chat', methods=['POST'])
@require_api_token
def web_chat_api():
    # Handle POST request
    try:
        data = request.json
        uid = data.get('user_id')
        msg = data.get('message')
        web_name = data.get('display_name')
        web_pic = data.get('picture_url')
        image_base64 = data.get('image')  # รูปภาพ base64 จากเว็บ
        image_type = data.get('image_type', 'jpg')  # ประเภทไฟล์

        if not uid: 
            return jsonify({"error": "Access Denied"}), 403
        
        existing_user = users_col.find_one({"line_user_id": uid})
        if not existing_user and (not web_name or not web_pic):
            return jsonify({"error": "New users must provide Profile Data"}), 403

        user = get_or_create_user(uid, "web", web_name, web_pic)

        # กรณีที่ส่งรูปภาพมาจากเว็บ (สำหรับการแจ้งร้องเรียน)
        if image_base64:
            if user.get('complaint_state') == 'waiting_image' and user.get('draft_desc'):
                try:
                    # [NEW] ตรวจสอบนามสกุลจาก image_type
                    if image_type.lower() not in ALLOWED_EXTENSIONS:
                        return jsonify({"error": f"นามสกุลไฟล์ .{image_type} ไม่รองรับ"}), 400

                    # ถอดรหัส base64
                    image_data = base64.b64decode(image_base64)
                    
                    # [NEW] ตรวจสอบขนาดข้อมูลหลังถอดรหัส
                    if len(image_data) > MAX_FILE_SIZE:
                        return jsonify({"error": f"ไฟล์มีขนาดใหญ่เกินไป (สูงสุด {MAX_FILE_SIZE // (1024*1024)}MB)"}), 400

                    # บันทึกลงไฟล์ชั่วคราว
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{image_type}') as tf:
                        tf.write(image_data)
                        temp_path = tf.name
                    
                    # เรียกใช้ฟังก์ชัน process_web_complaint_image
                    success_msg = process_web_complaint_image(user, temp_path)
                    
                    # บันทึกประวัติแชท
                    update_chat_history(uid, 'user', f'[ส่งรูปภาพแจ้งร้องเรียน: {user.get("draft_desc")}]')
                    update_chat_history(uid, 'model', success_msg)
                    
                    # บันทึกใน chat_history สำหรับ web
                    save_full_chat_history(uid, 'user', f'[ส่งรูปภาพแจ้งร้องเรียน: {user.get("draft_desc")}]', "web")
                    save_full_chat_history(uid, 'assistant', success_msg, "web")

                    return jsonify({
                        "reply": success_msg, 
                        "status": "success",
                        "is_registered": is_registered(user)
                    })
                    
                except Exception as e:
                    print(f"Web Image Processing Error: {e}")
                    return jsonify({"error": str(e)}), 500
                finally:
                    if 'temp_path' in locals() and os.path.exists(temp_path): os.remove(temp_path)
            else:
                # กรณีส่งรูปมาแต่ไม่ได้อยู่ในสถานะรอรูป (เช่น ส่งเล่น หรือส่งผิด)
                reply_msg = "📷 ได้รับรูปภาพแล้วค่ะ\nหากต้องการแจ้งร้องเรียน/แจ้งซ่อม กรุณาพิมพ์รายละเอียดปัญหาเข้ามาก่อนนะคะ แล้วระบบจะแจ้งให้ส่งรูปภาพอีกครั้งค่ะ"
                
                update_chat_history(uid, 'user', '[ส่งรูปภาพ]')
                update_chat_history(uid, 'model', reply_msg)
                save_full_chat_history(uid, 'user', '[ส่งรูปภาพ]', "web")
                save_full_chat_history(uid, 'assistant', reply_msg, "web")
                
                return jsonify({
                    "reply": reply_msg,
                    "status": "success",
                    "is_registered": is_registered(user)
                })
        
        # ถ้าไม่มีรูปภาพ (เป็นข้อความธรรมดา)
        if not msg: 
            return jsonify({
                "status": "connected", 
                "user_info": {
                    "line_user_id": user['line_user_id'],
                    "display_name": user.get('display_name'),
                    "picture_url": user.get('picture_url'),
                    "is_registered": is_registered(user)
                }
            })

        # ตรวจสอบว่าผู้ใช้ลงทะเบียนแล้วหรือยัง
        if not is_registered(user):
            current_name = user.get('display_name', 'ลูกบ้าน')
            
            # ถ้าข้อความไม่ใช่คำสั่งลงทะเบียน ให้แจ้งให้ลงทะเบียน
            if not msg.strip().startswith("ลงทะเบียน"):
                reply = (
                    f"สวัสดีคุณ {current_name}! 👋\n\n"
                    f"📝 กรุณาลงทะเบียนเพื่อใช้งานแชตบอตนิติบุคคล\n\n"
                    f"พิมพ์: ลงทะเบียน [เลขห้อง] [ชื่อ] [นามสกุล] [เบอร์โทร]\n\n"
                    f"ตัวอย่าง:\n"
                    f"ลงทะเบียน 814 สมชาย ใจดี 0812345678"
                )
                
                # บันทึกประวัติแชท
                update_chat_history(uid, 'user', msg)
                update_chat_history(uid, 'model', reply)
                
                # บันทึกใน chat_history สำหรับ web
                save_full_chat_history(uid, 'user', msg, "web")
                save_full_chat_history(uid, 'assistant', reply, "web")

                return jsonify({
                    "reply": reply, 
                    "status": "registration_required",
                    "is_registered": False
                })
        
        # ถ้าลงทะเบียนแล้ว
        update_chat_history(uid, 'user', msg)
        reply = process_text_logic(user, msg)
        update_chat_history(uid, 'model', reply)
        
        # บันทึกใน chat_history สำหรับ web
        save_full_chat_history(uid, 'user', msg, "web")
        save_full_chat_history(uid, 'assistant', reply, "web")

        return jsonify({
            "reply": reply, 
            "status": "success",
            "is_registered": is_registered(user)
        })

    except Exception as e:
        print(f"Web API Error: {e}")
        return jsonify({"error": str(e)}), 500

def process_web_complaint_image(user, image_path):
    """
    ประมวลผลรูปภาพการแจ้งร้องเรียนจากเว็บ (แก้ไขข้อความ)
    """
    try:
        uid = user['line_user_id']
        
        # 1. Upload to Cloudinary
        up_res = cloudinary.uploader.upload(
            image_path,
            folder="complaints",
            tags=["complaint", f"user:{uid}", "web"]
        )
        img_url = up_res.get('secure_url')
        user_desc = user.get('draft_desc')
        
        print(f"📸 เริ่มประมวลผลการแจ้งร้องเรียนจากเว็บ:")
        print(f"   ผู้ใช้: {user.get('first_name', 'Unknown')} (ห้อง {user.get('room_number', '-')})")
        print(f"   คำอธิบาย: {user_desc}")
        
        # 2. วิเคราะห์ความสำคัญจากคำอธิบาย
        desc_urgency = analyze_urgency_from_description(user_desc)
        print(f"   ความสำคัญจากคำอธิบาย: {desc_urgency}")
        
        # 3. AI Analysis
        ai_summary_text = user_desc 
        ai_urgency = "Medium"  # default

        try:
            print("🤖 อัพโหลดภาพไปยัง Gemini...")
            
            upload_file = client.files.upload(file=image_path)
            
            # รอให้ไฟล์พร้อมใช้งาน
            while upload_file.state.name == "PROCESSING":
                time.sleep(1)
                upload_file = client.files.get(name=upload_file.name)

            vision_prompt = (
                f"คำอธิบายจากลูกบ้าน: '{user_desc}'\n\n"
                
                "📋 วิเคราะห์รูปภาพนี้ประกอบกับคำอธิบายข้างต้น:\n\n"
                
                "เกณฑ์ความสำคัญ:\n"
                "🔴 HIGH (ต้องแก้ไขภายในวันนี้):\n"
                "   • ไฟไหม้ ไฟฟ้าลัดวงจร ไฟช็อต\n"
                "   • น้ำท่วมในห้อง ระบบประปาแตก\n"
                "   • แก๊สรั่ว กลิ่นแก๊ส\n"
                "   • ทางหนีไฟอุดตัน\n"
                "   • ประตูหน้าต่างเสียหายจนปิดล็อคไม่ได้\n\n"
                
                "🟡 MEDIUM (แก้ไขได้ภายใน 1-2 วัน):\n"
                "   • เครื่องปรับอากาศเสีย\n"
                "   • ระบบไฟฟ้าบางส่วนเสีย\n"
                "   • ประตูล็อคขัดข้อง\n"
                "   • ปั๊มน้ำไม่ทำงาน\n"
                "   • ส้วมตัน\n"
                "   • เครื่องทำน้ำร้อนเสีย\n\n"
                
                "🟢 LOW (แก้ไขได้ภายใน 3-5 วัน):\n"
                "   • สีผนังลอก\n"
                "   • ผนังร้าวเล็กน้อย\n"
                "   • ฝ้าเพดานมีจุดชื้น\n"
                "   • เครื่องใช้ไฟฟ้าขัดข้องเล็กน้อย\n"
                "   • ที่จับประตูหลวม\n\n"
                
                "หน้าที่ของคุณ:\n"
                "1. วิเคราะห์สิ่งที่เห็นในรูปภาพ\n"
                "2. เปรียบเทียบกับคำอธิบายที่ลูกบ้านแจ้งมา\n"
                "3. สรุปปัญหาเชิงเทคนิคและคาดการณ์สาเหตุที่เป็นไปได้แม้ลูกบ้านจะไม่ได้แจ้ง\n\n"

                "Format ตอบ: 'Summary || Urgency || Detailed_Analysis'\n"
                "- Summary: สรุปปัญหาทางเทคนิคสั้นๆ (ภาษาไทย) ไม่เกิน 100 ตัวอักษร\n"
                "- Urgency: ประเมินความเร่งด่วน (High, Medium, Low)\n"
                "- Detailed_Analysis: บทวิเคราะห์เชิงลึกจากภาพและคำอธิบาย (ภาษาไทย) ให้ข้อมูลเพิ่มเติมที่ AI เห็นจากรูปแต่ลูกบ้านอาจไม่ได้แจ้ง เช่น 'จากการตรวจสอบพบว่ามีความเสียหายลึกถึงโครงสร้าง' หรือ 'มีคราบน้ำจากการรั่วซึมมานาน' เป็นต้น\n"
            )
            
            print("🤖 กำลังวิเคราะห์ด้วย gemini-3-flash-preview...")
            gemini_res = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_uri(
                                file_uri=upload_file.uri,
                                mime_type=upload_file.mime_type
                            ),
                            types.Part.from_text(text=vision_prompt)
                        ]
                    )
                ]
            )
            
            raw_result = gemini_res.text.strip()
            print(f"🤖 ผลลัพธ์จาก AI Vision: {raw_result}")
            
            if "||" in raw_result:
                parts = raw_result.split("||")
                if len(parts) >= 3:
                    ai_summary_text = parts[0].strip()
                    ai_urgency = parts[1].strip()
                    detailed_analysis = parts[2].strip()
                    
                    final_ai_summary = f"{ai_summary_text}\n\n🤖 วิเคราะห์เชิงลึก:\n{detailed_analysis}"
                    print(f"🤖 วิเคราะห์ได้: Summary='{ai_summary_text}', Urgency='{ai_urgency}'")
                elif len(parts) == 2:
                    ai_summary_text = parts[0].strip()
                    ai_urgency = parts[1].strip()
                    final_ai_summary = ai_summary_text
                else:
                    final_ai_summary = raw_result
                    ai_urgency = "Medium"
            else:
                final_ai_summary = raw_result
                ai_urgency = "Medium"
                print(f"🤖 ไม่พบรูปแบบที่ถูกต้อง ใช้ค่า default: Urgency='{ai_urgency}'")

        except Exception as e:
            print(f"❌ Gemini Vision Error: {e}")
        
        # 4. ตัดสินใจขั้นสุดท้าย
        final_urgency = determine_final_urgency(desc_urgency, ai_urgency, user_desc)
        print(f"✅ ความสำคัญขั้นสุดท้าย: {final_urgency}")
        
        # 5. SAVE DB
        new_complaint = {
            "line_user_id": uid,
            "room_number": user.get('room_number'),
            "description": user_desc,
            "image_url": img_url,
            "status": "pending",
            "ai_summary": final_ai_summary,
            "urgency_level": final_urgency,
            "timestamp": get_bkk_now(),
            "priority": final_urgency.lower(),
            "platform": "web",
            "analysis_debug": {
                "desc_urgency": desc_urgency,
                "vision_urgency": ai_urgency,
                "final_decision": final_urgency,
                "user_description": user_desc
            }
        }
        
        complaints_col.insert_one(new_complaint)
        print(f"✅ บันทึกการร้องเรียนจากเว็บสำเร็จ: ID={new_complaint.get('_id')}")
        
        # 6. Clear State
        users_col.update_one(
            {"line_user_id": uid}, 
            {"$set": {"complaint_state": "normal", "draft_desc": None}}
        )
        
        # 7. สร้างข้อความตอบกลับ (แก้ไขข้อความ)
        success_msg = (
            f"✅ รับแจ้งร้องเรียนเรียบร้อยแล้วค่ะ!\n\n"
            f"📌 เรื่อง: {user_desc}\n"
            f"📷 ได้รับรูปภาพแล้ว\n"
            f"📊 ระดับความสำคัญ: {final_urgency}\n"
            f"เจ้าหน้าที่จะรีบดำเนินการตรวจสอบให้นะคะ ขอบคุณค่ะ 🙏"
        )
        
        return success_msg
        
    except Exception as e:
        print(f"❌ Error in process_web_complaint_image: {e}")
        import traceback
        traceback.print_exc()
        return "เกิดข้อผิดพลาดในการประมวลผลค่ะ โปรดลองอีกครั้ง"

# ================= 6. เพิ่ม API สำหรับตรวจสอบการวิเคราะห์ (สำหรับ debugging) =================

@app.route('/api/debug/analyze', methods=['POST'])
@require_api_token
def debug_analyze_urgency():
    """API สำหรับทดสอบการวิเคราะห์ความสำคัญ"""
    try:
        data = request.json
        user_desc = data.get('description', '')
        
        if not user_desc:
            return jsonify({"error": "Description required"}), 400
        
        # วิเคราะห์จากคำอธิบาย
        desc_urgency = analyze_urgency_from_description(user_desc)
        
        return jsonify({
            "description": user_desc,
            "desc_urgency": desc_urgency,
            "analysis_rules": {
                "high_keywords": ["ไฟไหม้", "ไฟฟ้าลัดวงจร", "น้ำท่วม", "แก๊สรั่ว"],
                "medium_keywords": ["แอร์เสีย", "ไฟฟ้าเสีย", "ประตูเสีย"],
                "low_keywords": ["สีลอก", "ผนังร้าว", "ฝ้าเพดาน"]
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ================= CHAT HISTORY API =================

@app.route('/api/chat-history/<user_id>', methods=['GET'])
@require_api_token
def get_chat_history(user_id):
    """ดึงประวัติแชททั้งหมดของผู้ใช้"""
    try:
        # ดึงประวัติจาก collection chat_history
        history = list(chat_history_col.find(
            {"line_user_id": user_id}
        ).sort("timestamp", 1).limit(100))  # เรียงจากเก่าไปใหม่
        
        result = []
        for item in history:
            result.append({
                "role": item.get("role", ""),
                "message": item.get("message", ""),
                "platform": item.get("platform", "line"),
                "timestamp": item.get("timestamp", "").strftime("%Y-%m-%d %H:%M:%S") if item.get("timestamp") else ""
            })
        
        return jsonify({"history": result})
    except Exception as e:
        print(f"Chat History Error: {e}")
        return jsonify({"error": str(e)}), 500

# ================= USER STATUS API =================

@app.route('/api/web/user-status', methods=['GET'])
def check_user_registration_status():
    """ตรวจสอบสถานะการลงทะเบียนของผู้ใช้"""
    try:
        # ดึง user_id จาก query parameter
        user_id = request.args.get('user_id')
        
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        # ค้นหาผู้ใช้
        user = users_col.find_one({"line_user_id": user_id})
        
        if not user:
            return jsonify({
                "exists": False,
                "is_registered": False,
                "message": "User not found"
            })
        
        # ตรวจสอบการลงทะเบียน
        registered = is_registered(user)
        
        # ข้อมูลที่จะส่งกลับ
        response_data = {
            "exists": True,
            "is_registered": registered,
            "user_info": {
                "line_user_id": user.get('line_user_id'),
                "display_name": user.get('display_name'),
                "picture_url": user.get('picture_url'),
                "first_name": user.get('first_name'),
                "last_name": user.get('last_name'),
                "room_number": user.get('room_number'),
                "phone_number": user.get('phone_number'),
                "platform": user.get('platform', 'line')
            }
        }
        
        # ถ้ายังไม่ลงทะเบียน ให้เพิ่มคำแนะนำ
        if not registered:
            response_data["registration_guide"] = {
                "format": "ลงทะเบียน [เลขห้อง] [ชื่อ] [นามสกุล] [เบอร์โทร]",
                "example": "ลงทะเบียน 814 สมชาย ใจดี 0812345678"
            }
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"User Status Error: {e}")
        return jsonify({"error": str(e)}), 500

# ================= ROOT ENDPOINT =================

@app.route('/')
def home():
    return "Smart Condo Backend API is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(host='0.0.0.0', port=port, debug=debug_mode)