import os
import json
import datetime
import tempfile
import random
import time
import base64
from functools import wraps, lru_cache
from bson import ObjectId
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from dotenv import load_dotenv
import csv
import io
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
import pytz
import requests # Move to top for performance

# Google GenAI (New SDK)
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
    ReplyMessageRequest, PushMessageRequest, TextMessage, ImageMessage, FlexMessage, FlexContainer
)
from flex_templates import create_text_flex, create_parcel_carousel, create_complaint_update_flex, create_parcel_pickup_flex, create_after_hours_selection_flex, create_after_hours_confirmation_flex
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
    
    # Collections
    users_col = db["users"]
    parcels_col = db["parcels"]
    complaints_col = db["complaints"]
    kb_col = db["knowledge_base"]
    admins_col = db["admins"]
    audit_logs_col = db["audit_logs"]
    chat_history_col = db["chat_history"]

    # Consolidated index creation logic
    def ensure_indexes():
        """สร้าง Indexes เพื่อเพิ่มความเร็วในการค้นหา"""
        try:
            # Users: ค้นหาตาม line_user_id (Unique)
            try:
                # If existing index is not unique, we'll catch the error and move on
                users_col.create_index([("line_user_id", 1)], unique=True)
            except:
                users_col.create_index([("line_user_id", 1)])
            
            users_col.create_index([("platform", 1)])
            users_col.create_index([("last_active", -1)])
            users_col.create_index([("room_number", 1)])
            
            # Complaints: ค้นหาตาม status, priority, timestamp (NOT Unique for user)
            complaints_col.create_index([("status", 1)])
            complaints_col.create_index([("priority", 1)])
            complaints_col.create_index([("timestamp", -1)])
            complaints_col.create_index([("line_user_id", 1)])
            complaints_col.create_index([("status", 1), ("priority", -1), ("timestamp", -1)])
            complaints_col.create_index([("room_number", 1)])
            
            # Parcels: ค้นหาตาม status, pin, timestamp, is_after_hours
            parcels_col.create_index([("status", 1)])
            try:
                parcels_col.create_index([("pin", 1)], unique=True)
            except:
                parcels_col.create_index([("pin", 1)])
            
            parcels_col.create_index([("timestamp", -1)])
            parcels_col.create_index([("status", 1), ("timestamp", -1)])
            parcels_col.create_index([("room_number", 1)])
            parcels_col.create_index([("is_after_hours", 1)])  # สำหรับการแยกพัสดุนอกเวลา
            parcels_col.create_index([("status", 1), ("is_after_hours", 1)])  # Compound index
            
            # Audit Logs
            audit_logs_col.create_index([("timestamp", -1)])
            
            # Chat history
            chat_history_col.create_index([("line_user_id", 1), ("timestamp", -1)])
            
            print("✅ MongoDB Indexes ensured.")
        except Exception as e:
            print(f"⚠️ Failed to create indexes: {e}")

    ensure_indexes()
    
    print("✅ MongoDB Connected: smart_condo")
    # ตรวจสอบจำนวนข้อมูลเบื้องต้น
    print(f"📊 Database Stats:")
    print(f"   - Users: {users_col.count_documents({})}")
    print(f"   - Parcels: {parcels_col.count_documents({})}")
    print(f"   - Complaints: {complaints_col.count_documents({})}")
    print(f"   - Admins: {admins_col.count_documents({})}")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")

# Initialize ThreadPoolExecutor for background tasks (Increased for speed)
executor = ThreadPoolExecutor(max_workers=50)

# Setup Gemini Client (New SDK)
client = genai.Client(api_key=GEMINI_API_KEY)

# ================= CLOUDINARY SETUP =================
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# Redundant index creation removed (consolidated in ensure_indexes)

# ================= LINE BOT CONFIGURATION =================
line_configuration = Configuration(
    access_token=os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
)

line_handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

@app.before_request
def log_request_info():
    if request.path.startswith('/api'):
        print(f"🔍 Incoming Request: {request.method} {request.path}")

def get_bkk_now():
    """Get current usage time in Bangkok timezone (UTC+7)"""
    tz = datetime.timezone(datetime.timedelta(hours=7))
    return datetime.datetime.now(tz)

def analyze_urgency_from_description(user_desc):
    """
    วิเคราะห์ความสำคัญเบื้องต้นจากข้อความที่ผู้ใช้แจ้ง
    """
    try:
        if not user_desc: return "Low"
        user_desc_lower = user_desc.lower()
        
        # เกณฑ์ความสำคัญ:
        # 🔴 HIGH (ต้องแก้ไขภายในวันนี้)
        high_keywords = [
            "ไฟไหม้", "ไฟลุก", "ไฟช็อต", "ไฟฟ้าลัดวงจร", "ไฟดูด", "ไฟสปาร์ค",
            "ไฟดับ", "ดับไฟ", "ไฟหมด", "ไฟดับทั้งหมด", "ไฟดับทั้งคอนโด", "ไฟดับทั้งอาคาร",
            "เสาไฟล้ม", "เสาไฟ", "เสาล้ม", "เสาโค่น", "เสาไฟโค่น", "เสาไฟฟ้าล้ม",
            "น้ำท่วม", "น้ำรั่วมาก", "น้ำซึมมาก", "น้ำแตก", "ท่อน้ำแตก", "ท่อประปาแตก",
            "แก๊สรั่ว", "กลิ่นแก๊ส", "แก๊สหอบ", "แก๊สผิดปกติ",
            "ทางหนีไฟอุดตัน", "บันไดหนีไฟ", "ทางหนีไฟ",
            "ประตูหน้าต่างเสียหาย", "ล็อคไม่ได้", "ปิดล็อคไม่ได้", "ประตูพัง", "หน้าต่างพัง",
            "โจร", "ขโมย", "ปล้น", "งัดแงะ", "อันตราย", "ฉุกเฉิน", "ด่วนมาก", "ระเบิด"
        ]
        
        # 🟡 MEDIUM (แก้ไขได้ภายใน 1-2 วัน)
        medium_keywords = [
            "เครื่องปรับอากาศ", "แอร์เสีย", "แอร์ไม่เย็น", "แอร์รั่ว", "แอร์น้ำหยด",
            "ไฟฟ้าบางส่วนเสีย", "ไฟไม่ติด", "สวิทช์เสีย", "ปลั๊กไฟเสีย", "เบรกเกอร์",
            "ประตูล็อคขัดข้อง", "ล็อคประตู", "กุญแจ", "ลูกบิดเสีย",
            "ปั๊มน้ำ", "น้ำไม่ไหล", "น้ำอ่อน", 
            "ส้วมตัน", "ชักโครก", "ท่อตัน", "กดไม่ลง",
            "เครื่องทำน้ำร้อน", "เครื่องทำน้ำอุ่น", "น้ำไม่ร้อน"
        ]
        
        # 🟢 LOW (แก้ไขได้ภายใน 3-5 วัน)
        low_keywords = [
            "สีลอก", "สีผนังลอก", "สีร่อน",
            "ผนังร้าว", "รอยร้าว", "ร้าวเล็กน้อย",
            "ฝ้าเพดาน", "ฝ้ารั่ว", "จุดชื้น", "คราบน้ำ",
            "เครื่องใช้ไฟฟ้าขัดข้อง", "เครื่องใช้ไฟฟ้า",
            "ที่จับประตูหลวม", "ลูกบิดหลวม", "บานพับ",
            "มุ้งลวด", "หลอดไฟ", "ไฟกระพริบ"
        ]
        
        for kw in high_keywords:
            if kw in user_desc_lower: return "High"
        for kw in medium_keywords:
            if kw in user_desc_lower: return "Medium"
        for kw in low_keywords:
            if kw in user_desc_lower: return "Low"
            
        return "Low"
    except Exception as e:
        print(f"❌ Urgency Description Analysis Error: {e}")
        return "Medium"

def determine_final_urgency(desc_urgency, ai_urgency, user_desc):
    """
    กำหนดความสำคัญขั้นสุดท้ายโดยพิจารณาจากทั้งสองแหล่ง
    น้ำหนัก: AI Vision (รูป) 80%, Description 20%
    """
    try:
        user_desc_lower = user_desc.lower() if user_desc else ""
        
        # Normalize inputs
        desc_urgency = (desc_urgency or "Low").capitalize()
        ai_urgency = (ai_urgency or "Low").capitalize()
        
        # 🔥 กฎพิเศษ (Safety First): ถ้ามีคำว่า "ไฟไหม้" ในรูป หรืออันตรายร้ายแรง
        # ให้สรุปเป็น High ทันที (เพราะปกติ AI Vision จะจับได้)
        emergency_keywords = ["ไฟไหม้", "ไฟลุก", "ไฟฟ้าลัดวงจร", "ประกายไฟ", "น้ำท่วม", "แก๊สรั่ว", "ระเบิด", "ไฟฟ้าช็อต"]
        if ai_urgency == "High" and any(kw in user_desc_lower for kw in emergency_keywords):
            print(f"🔥 EMERGENCY DETECTED: AI={ai_urgency}, Desc contains emergency keywords")
            return "High"
        
        # แปลง urgency เป็น score (High=3, Medium=2, Low=1)
        urgency_map = {"High": 3, "Medium": 2, "Low": 1}
        ai_score = urgency_map.get(ai_urgency, 1)
        desc_score = urgency_map.get(desc_urgency, 1)
        
        # คำนวณ weighted score (AI 80%, Desc 20%)
        final_score = (ai_score * 0.8) + (desc_score * 0.2)
        
        # แปลง score กลับเป็น urgency level
        # final_score: 1.0-1.66 = Low, 1.67-2.33 = Medium, 2.34-3.0 = High
        if final_score >= 2.4:  # เกือบ High (2.4/3 = 80%)
            final_urgency = "High"
        elif final_score >= 1.6:  # ระหว่าง Low-Medium
            final_urgency = "Medium"
        else:
            final_urgency = "Low"
        
        print(f"📊 Urgency Calculation (Weighted 80/20):")
        print(f"   AI Vision: {ai_urgency} (score={ai_score}, weight=0.8)")
        print(f"   Description: {desc_urgency} (score={desc_score}, weight=0.2)")
        print(f"   Final Score: {final_score:.2f} → {final_urgency}")
        
        return final_urgency
        
    except Exception as e:
        print(f"❌ Urgency Decision Error: {e}")
        return "Medium"

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

def save_full_chat_history(line_user_id, role, message, platform="line", image_url=None):
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
            "image_url": image_url,
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

def send_line_message(user_id, message=None, image_url=None, flex_contents=None):
    """ส่งข้อความ LINE ไปยังผู้ใช้ (รองรับ Flex Message)"""
    try:
        with ApiClient(line_configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            messages = []
            
            # 1. กรณีส่งเป็น Flex Message
            if flex_contents:
                try:
                    flex_message = FlexMessage(
                        alt_text="ข้อความใหม่จาก Smart Condo",
                        contents=FlexContainer.from_dict(flex_contents)
                    )
                    messages.append(flex_message)
                except Exception as flex_err:
                    print(f"❌ Flex Construction Error: {flex_err}")
                    # Fallback to text
                    messages.append(TextMessage(text=message or "มีข้อความใหม่ (แสดงผลไม่ได้)"))
            
            # 2. กรณีส่งเป็น Text (หรือ Fallback)
            elif message:
                # ถ้าข้อความสั้นๆ อาจจะส่งเป็น Text ธรรมดา หรือจะห่อเป็น Flex ก็ได้
                # ในที่นี้ถ้าไม่ได้ส่ง flex_contents มาโดยตรง เราจะส่งเป็น Text ธรรมดาไปก่อน
                # หรือถ้าอยากให้สวยงามตลอดเวลา ก็เรียก create_text_flex(message) ได้
                messages.append(TextMessage(text=message))
            
            # 3. กรณีมีรูปภาพแนบมาด้วย
            if image_url and image_url.strip() and image_url != "":
                try:
                    messages.append(ImageMessage(
                        original_content_url=image_url, 
                        preview_image_url=image_url
                    ))
                except Exception as img_error:
                    print(f"⚠️ Image Error: {img_error}")
            
            if not messages:
                return False

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

# ปรับให้มีความเป็นมนุษย์ สุภาพ และเห็นอกเห็นใจมากขึ้น และตอบกระชับ
CHAT_SYSTEM_PROMPT = """
คุณคือ "น้องบอตนิติ" ผู้ช่วยอัจฉริยะประจำคอนโดลุมพินี พาร์ค
บุคลิก: เป็นมนุษย์ (AI with Human Touch), สุภาพมาก, มีความเห็นอกเห็นใจ (Empathy), กระตือรือร้นที่จะช่วยเหลือ และดูเป็นมืออาชีพแต่เข้าถึงง่าย

หลักการสื่อสารแบบมนุษย์ (Human-Like Communication):
1. **ภาษาเป็นธรรมชาติ:** ใช้คำเชื่อมประโยคที่ลื่นไหล เช่น "อ้อ สำหรับเรื่องนี้...", "ไม่ต้องกังวลนะคะ เดี๋ยวบอตช่วยเช็กให้ค่ะ"
2. **แสดงความใส่ใจ:** หากลูกบ้านแจ้งปัญหา (เช่น น้ำรั่ว, แอร์เสีย) ให้แสดงความเห็นอกเห็นใจก่อนเริ่มตอบข้อมูล
3. **ใช้หางเสียงเหมาะสม:** ใช้ "ค่ะ/คะ" หรือ "ครับ" อย่างเหมาะสม โดยเน้นความเป็น "น้องบอตนิติ" ที่น่ารัก
4. **ไม่ตอบเป็นหุ่นยนต์:** หลีกเลี่ยงการตอบเป็นข้อๆ ที่แห้งแล้งเกินไป ให้บรรยายแบบบทสนทนาที่อ่านง่าย
5. **[สำคัญ] ตอบกระชับ:** ไม่อธิบายยืดยาว ตรงประเด็น ได้ใจความ ไม่เพ้อเจ้อ

กฎการตอบ (Strict Rules):
1. **ลำดับความสำคัญ:** 
   - ให้โฟกัสและตอบ "คำถามล่าสุดของผู้ใช้" ให้ตรงประเด็นที่สุดก่อน
   - **ห้าม** แทรกเรื่องพัสดุหรือสถานะการร้องเรียน หากผู้ใช้ถามเรื่องอื่น (เช่น กฎระเบียบ, เบอร์โทร, วิธีใช้) ให้ตอบเรื่องนั้นเพียวๆ
   - **ห้าม** นำข้อมูลส่วน "รายการพัสดุ:" หรือ "ประวัติแจ้งร้องเรียน" มาตอบเมื่อผู้ใช้ไม่ได้ถามถึง
   - ให้แจ้งเตือนพัสดุ/งานร้องเรียน ก็ต่อเมื่อ:
     ก. ผู้ใช้ถามถึงโดยเฉพาะ (เช่น "มีของมาส่งไหม", "สถานะร้องเรียนถึงไหน", "มีพัสดุไหม")
     ข. **เท่านั้น** ไม่ต้องแจ้งพัสดุเมื่อผู้ใช้แค่ทักทาย (เช่น "สวัสดี") หรือถามเรื่องทั่วไป

2. **การตอบเรื่องพัสดุ:**
   - หากใน Context มีข้อมูลส่วน "รายการพัสดุ:" และผู้ใช้ถามถึงพัสดุโดยเฉพาะ ให้ Copy ข้อความในส่วนนั้นมาตอบผู้ใช้ **ทั้งดุ้น** ทันที (ห้ามสรุปใหม่ ห้ามเปลี่ยนคำ) เพื่อความถูกต้องของข้อมูล

3. **ข้อมูลส่วนตัว:** ยึดข้อมูลใน [Context] อย่างเคร่งครัด
   - ถ้า Context ระบุ "ไม่มีประวัติการแจ้งร้องเรียน" ห้ามแสดงความยินดีหรือพูดถึงเรื่องนี้
   - ถ้าไม่ได้ถามเรื่องพัสดุ/ร้องเรียน ไม่ต้องพูดถึงข้อมูลเหล่านั้น

4. **ขอบเขต:** หากถามเรื่องที่ไม่มีข้อมูล ให้ตอบอย่างสุภาพว่า "ขออภัยค่ะ น้องบอตยังไม่มีข้อมูลส่วนนี้ในระบบเลย รบกวนติดต่อสำนักงานนิติฯ อาคาร A ชั้น G หรือโทร 02-689-6888 นะคะ"

5. **[CRITICAL] ความเป็นส่วนตัวผู้อื่น:** 
   - ห้ามเปิดเผย หรือตรวจสอบข้อมูลของ "ห้องอื่น" หรือ "บุคคลอื่น" โดยเด็ดขาด

6. **การขึ้นบรรทัดใหม่ในการตอบ:** 
   - จัดรูปแบบข้อความให้อ่านง่าย สบายตา ไม่เป็นก้อนข้อความยาวๆ

7. **[IMPORTANT] การตอบคำทักทาย:**
   - ตอบทักทายกลับแบบมนุษย์ที่สดใส เช่น "สวัสดีค่ะ คุณ[ชื่อ] วันนี้มีอะไรให้น้องบอตนิติช่วยดูแลไหมคะ?"
   - **ห้าม** นำข้อมูลพัสดุหรือประวัติร้องเรียนมาตอบในคำทักทายสั้นๆ

8. **[IMPORTANT] การใช้ชื่อผู้ใช้:**
   - เมื่อระบุชื่อผู้ใช้ ให้เว้นวรรคหน้าคำว่า คุณตามด้วยชื่อ แล้วเว้นวรรคหลังด้วย
   - ตัวอย่างที่ถูก: "สวัสดีค่ะ คุณสมชาย วันนี้มีอะไรให้ช่วยไหมคะ"
   - ตัวอย่างที่ผิด: "สวัสดีค่ะคุณสมชายวันนี้มีอะไรให้ช่วยไหมคะ" (ไม่มีการเว้นวรรค)
"""

@lru_cache(maxsize=128)
def extract_keywords(user_text):
    """
    สกัด Keyword จากข้อความโดยใช้ AI และเพิ่ม Cache
    ปรับ Prompt ให้สกัดคำที่ใช้ค้นหาในคู่มือได้แม่นยำขึ้น
    """
    try:
        analysis_prompt = (
            f"จงวิเคราะห์ข้อความของผู้ใช้: '{user_text}'\n"
            "สกัดคำหลัก (Keywords) ภาษาไทย 2-3 คำ ที่ครอบคลุมสาระสำคัญสำหรับการค้นหาในคู่มือดิจิทัลของนิติบุคคลคอนโด\n"
            "เน้นคำที่เป็น: อุปกรณ์ (เช่น แอร์, ท่อ), กฎระเบียบ (เช่น สัตว์เลี้ยง, ที่จอดรถ), หรือกิจกรรม (เช่น จ่ายค่ากลาง, จองห้องประชุม)\n"
            "ตัดคำขยายหรือคำฟุ่มเฟือยออก ตอบเฉพาะคำหลักคั่นด้วยช่องว่างเท่านั้น"
        )
        keyword_res = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=analysis_prompt
        )
        return keyword_res.text.strip().split()
    except:
        return []

def get_knowledge_context(user_text, user):
    """
    ดึงข้อมูล Context ทั้งหมด:
    1. ข้อมูลส่วนตัว (Users)
    2. พัสดุของห้องตัวเอง (Parcels)
    3. การแจ้งร้องเรียนของตัวเอง (Complaints)
    4. ความรู้ทั่วไป (Knowledge Base)
    """
    context_parts = []
    
    try:
        # --- PART 1: ข้อมูลส่วนตัว (Personal Data) ---
        user_info = f"ผู้ใช้งาน: {user.get('first_name', 'ลูกบ้าน')} {user.get('last_name', '')} (ห้อง {user.get('room_number', 'ไม่ระบุ')})"
        
        # 1.1 Parcels (ดูเฉพาะห้องตัวเอง)
        # ข้อมูลพัสดุจะถูกนำไปใช้ในฟังก์ชัน process_text_logic เท่านั้น
        parcel_context = f"รายการพัสดุ:\n🏠 ห้อง {user.get('room_number', '-')}\n📦 ตอนนี้ยังไม่มีพัสดุค้างอยู่นะคะ" # Default ไม่มีพัสดุ
        
        if user.get('room_number'):
            # ค้นหาพัสดุของห้องตัวเอง (ใช้ Regex เพื่อความยืดหยุ่น เช่น "814" หรือ "ห้อง 814")
            room_clean = str(user['room_number']).replace("ห้อง", "").strip()
            my_parcels = list(parcels_col.find({
                "room_number": {"$regex": f".*{room_clean}.*"}, 
                "status": "pending"
            }))
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
        ai_keywords = extract_keywords(user_text)
        
        # ค้นหาใน Knowledge Base แบบ Hybrid (DB Search -> Python Re-ranking)
        search_query = {}
        if ai_keywords:
            or_conditions = []
            for kw in ai_keywords:
                or_conditions.append({"topic": {"$regex": kw, "$options": "i"}})
                or_conditions.append({"content": {"$regex": kw, "$options": "i"}})
            search_query = {"$or": or_conditions}
        
        # 1. Fetch Candidates (ดึงมา 15 รายการเพื่อมาจัดอันดับต่อ)
        candidates = list(kb_col.find(search_query).limit(15))
        
        scored_results = []
        user_text_lower = user_text.lower()

        # 2. Smart Re-ranking (Scoring Logic เพื่อความแม่นยำสูงสุด)
        for doc in candidates:
            topic = str(doc.get('topic', '')).lower()
            content = str(doc.get('content', '')).lower()
            score = 0
            
            # กฎคะแนนที่แม่นกว่าเดิม:
            # - ถ้าเจอใน Topic ให้คะแนน 15 (สำคัญกว่ามาก)
            # - ถ้าเจอใน Content ให้คะแนน 5
            # - ถ้าเจอทั้งประโยค (Exact Phrase) ให้คะแนนพิเศษ 30
            for kw in ai_keywords:
                kw_low = kw.lower()
                if kw_low in topic: score += 15
                if kw_low in content: score += 5
            
            if user_text_lower in topic or user_text_lower in content:
                score += 30
            
            if score > 0:
                scored_results.append((score, f"หัวข้อ: {doc.get('topic')}\nรายละเอียด: {doc.get('content')}"))

        # 3. Sort by score (เอาตัวที่แม่นที่สุด 3 อันดับแรก)
        scored_results.sort(key=lambda x: x[0], reverse=True)
        top_knowledge = [res[1] for res in scored_results[:3]]

        if top_knowledge:
            kb_str = "[คลังความรู้ (Knowledge Base)]\n" + "\n---\n".join(top_knowledge)
            context_parts.append(kb_str)
        else:
            context_parts.append("[คลังความรู้ (Knowledge Base)]\nขออภัยค่ะ ไม่พบข้อมูลที่เกี่ยวข้องในคู่มือเลย")

        return "\n\n".join(context_parts)
    except Exception as e:
        print(f"RAG Error: {e}")
        return None

@lru_cache(maxsize=128)
def analyze_intent(text):
    """
    วิเคราะห์ความตั้งใจของผู้ใช้ (AI Intent Analysis) 
    เพิ่ม Cache เพื่อความเร็ว และใช้ Model ที่เล็กลง (8b) เพื่อความไว
    """
    try:
        text_clean = text.strip().lower()
        
        # Rule-based check ก่อน (ไวกว่า AI)
        rule_keywords = ["กฎการแจ้งร้องเรียน", "กฎการร้องเรียน", "รายละเอียดการแจ้งร้องเรียน", 
                        "วิธีแจ้งร้องเรียน", "ขั้นตอนการแจ้งร้องเรียน", "ขอทราบการแจ้งร้องเรียน",
                        "อยากทราบการแจ้งร้องเรียน", "อยากรู้การแจ้งร้องเรียน",
                        "กฎแจ้งร้องเรียน", "วิธีร้องเรียน", "ขั้นตอนร้องเรียน",
                        "อยากรู้วิธีแจ้งร้องเรียน", "อยากรู้ขั้นตอนแจ้งร้องเรียน"]
        
        if any(keyword in text_clean for keyword in rule_keywords):
            return "GENERAL"
        
        general_keywords = ["สูบบุหรี่", "กฎการจอด", "เบอร์ตำรวจ", "กฎระเบียบ", 
                           "เบอร์โทร", "เบอร์ฉุกเฉิน", "วิธีใช้", "บริการ",
                           "ค่าบริการ", "ทำยังไง", "อย่างไร", "สอบถาม"]
        
        if any(keyword in text_clean for keyword in general_keywords):
            return "GENERAL"
        
        prompt = (
            f"Classify user intent: '{text}'\n"
            "Categories:\n"
            "1. COMPLAINT_START: User wants to report an issue but hasn't provided details yet (e.g., 'แจ้งร้องเรียน', 'มีปัญหาครับ', 'ร้องเรียนหน่อย', 'แจ้งเรื่อง').\n"
            "2. COMPLAINT_DETAIL: User provides specific details of a problem (e.g., 'ไฟทางเดินเสีย', 'น้ำรั่วที่ระเบียง', 'แอร์ไม่เย็นเลย', 'ไฟติดๆดับๆ').\n"
            "3. CANCEL: User wants to cancel or says they don't want to report anymore, including typos (e.g., 'ยกเลิก', 'ไม่แจ้งแล้ว', 'ไม่เจ้ง', 'ไม่เเจ่งล้', 'พอแล้ว').\n"
            "4. CHECK_STATUS: Asking about ticket status.\n"
            "5. GENERAL: General questions to the bot or about rules/info.\n"
            "6. OTHER: Greetings or unrelated.\n"
            "Return ONLY the category name."
        )
        
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt
        )
        intent_result = response.text.strip().upper()
        
        # Safety normalization
        if "CANCEL" in intent_result: return "CANCEL"
        if "CHECK_STATUS" in intent_result: return "CHECK_STATUS"
        if "COMPLAINT_START" in intent_result: return "COMPLAINT_START"
        if "COMPLAINT_DETAIL" in intent_result: return "COMPLAINT_DETAIL"
        if "GENERAL" in intent_result: return "GENERAL"
        
        return "OTHER"
    except Exception as e:
        print(f"⚠️ Intent Analysis Error: {e}")
        return "OTHER"

def update_chat_history(uid, role, message, platform="line", image_url=None):
    """
    อัพเดตประวัติการสนทนาใน Users collection และ Chat History collection
    """
    if role == 'assistant': role = 'model'
    entry = {"role": role, "parts": [message], "timestamp": datetime.datetime.utcnow()}
    if image_url:
        entry["image_url"] = image_url

    users_col.update_one(
        {"line_user_id": uid},
        {"$push": {"chat_history": {"$each": [entry], "$slice": -10}}}
    )
    
    # บันทึกใน chat_history collection ด้วย (ใช้ platform ที่ระบุ)
    save_full_chat_history(uid, role, message, platform, image_url)
    
    return entry["timestamp"]

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

# ================= AFTER-HOURS PARCEL HELPERS =================



def detect_after_hours_intent(text):
    """
    ตรวจจับความต้องการรับพัสดุนอกเวลา และระบุพัสดุ (ถ้ามี)
    Returns: (is_intent, target_pins)
    """
    try:
        prompt = f"""วิเคราะห์ข้อความว่าผู้ใช้ต้องการ **ลงทะเบียน/ยืนยันรับพัสดุนอกเวลา** หรือไม่

ข้อความ: "{text}"

Output Format (JSON):
{{
  "intent": "YES" or "NO",
  "target_pins": ["12345"] or "ALL" or []
}}

Rules:
1. YES ถ้าต้องการรับพัสดุนอกเวลา (เช่น "ขอรับนอกเวลา", "รับนอกเวลาเลข 12345", "รับตอนดึก")
2. NO ถ้าเป็นคำถาม หรือเรื่องอื่น
3. target_pins:
   - ถ้ามีเลขพัสดุ/PIN ในข้อความ ให้ใส่ใน list
   - ถ้าบอกว่า "ทั้งหมด" หรือ "ทุกชิ้น" ให้ใส่ "ALL"
   - ถ้าไม่ระบุเลข ให้ใส่ []
"""

        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        import json
        result = json.loads(response.text.strip())
        is_intent = result.get("intent") == "YES"
        target_pins = result.get("target_pins")
        
        # Normalize
        if target_pins == "ALL":
            target_pins = "ALL"
        elif isinstance(target_pins, list):
            target_pins = [str(p) for p in target_pins]
        else:
            target_pins = []

        return is_intent, target_pins
        
    except Exception as e:
        print(f"❌ After-Hours Intent Error: {e}")
        # Fallback keyword matching
        text_lower = text.lower()
        question_keywords = ["ทำไง", "ได้ไหม", "ได้มั้ย", "ยังไง", "อย่างไร", "คือ", "เวลาไหน", "?"]
        if any(kw in text_lower for kw in question_keywords):
            return False, []
        
        return is_intent, []

def interpret_parcel_selection(text, total_items):
    """
    แปลความหมายการเลือกพัสดุจากข้อความ (Natural Language to Indices)
    รองรับ: "1-3", "1 ถึง 3", "ทั้งหมด", "อันแรกกับอันสุดท้าย"
    Returns: list of 0-based indices e.g., [0, 2]
    """
    try:
        prompt = f"""Human wants to select items from a list of {total_items} items.
Text: "{text}"

Output JSON only: specific 1-based indices.
Rules:
- "ทั้งหมด", "all", "ทุกอัน" -> all indices [1, 2, ..., {total_items}]
- "1-3", "1 to 3", "1 ถึง 3" -> [1, 2, 3]
- "1, 3" -> [1, 3]
- "อันแรก" -> [1]
- If invalid/unsure -> []

Example JSON: {{"indices": [1, 2, 3]}}"""

        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        import json
        result = json.loads(response.text.strip())
        indices = result.get("indices", [])
        
        # Validate indices
        valid_indices = []
        for idx in indices:
            if 1 <= idx <= total_items:
                valid_indices.append(idx - 1) # Convert to 0-based
        
        return valid_indices
        
    except Exception as e:
        print(f"❌ Selection Interpretation Error: {e}")
        return []

def detect_after_hours_cancel_intent(text):
    """
    ตรวจจับความต้องการ **ยกเลิก** รับพัสดุนอกเวลา และระบุพัสดุ (ถ้ามี)
    Returns: (is_cancel, target_pins)
    - is_cancel (bool): True ถ้าต้องการยกเลิก
    - target_pins (list): รายการ PIN ที่ต้องการยกเลิก ถ้าเป็น None/Empty หมายถึง "ทั้งหมด" หรือ "ไม่ระบุ"
    """
    try:
        prompt = f"""วิเคราะห์ข้อความของผู้ใช้เกี่ยวกับพัสดุว่าต้องการ "ยกเลิกการรับนอกเวลา" หรือไม่

ข้อความ: "{text}"

Output Format (JSON):
{{
  "intent": "CANCEL" or "NO",
  "target_pins": ["12345", "67890"] or "ALL" or []
}}

Rules:
1. INTENT = "CANCEL" ถ้าผู้ใช้ต้องการยกเลิกรับนอกเวลา (เช่น "ไม่รับนอกเวลาแล้ว", "ยกเลิกอันแรก", "ยกเลิก 12345", "เปลี่ยนใจ")
2. INTENT = "NO" ถ้าเป็นเรื่องอื่น หรือยืนยันการรับ
3. target_pins:
   - ถ้าระบุเลขพัสดุ/PIN ชัดเจน ให้ใส่ใน list
   - ถ้าพูดว่า "ทั้งหมด", "ทุกอัน" ให้ใส่ "ALL"
   - ถ้าไม่ได้ระบุเจาะจง ให้ใส่ [] (Empty List)
"""

        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        import json
        result = json.loads(response.text.strip())
        is_cancel = result.get("intent") == "CANCEL"
        target_pins = result.get("target_pins")
        
        # Normalize target_pins
        if target_pins == "ALL":
            target_pins = "ALL"
        elif isinstance(target_pins, list):
            target_pins = [str(p) for p in target_pins]
        else:
            target_pins = []

        return is_cancel, target_pins
        
    except Exception as e:
        print(f"❌ Cancel Intent Error: {e}")
        # Fallback keyword matching
        cancel_keywords = ["ยกเลิกรับนอกเวลา", "ไม่รับนอกเวลา", "เปลี่ยนใจ", "รับในเวลาปกติ", "ยกเลิกการรับนอกเวลา"]
        is_cancel = any(kw in text.lower() for kw in cancel_keywords)
        return is_cancel, []

# ================= REGISTRATION HANDLER =================


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
    
    # ================= PRIORITY CANCELLATION (COMPLAINT STATUS) =================
    # ตรวจสอบว่ากำลังแจ้งร้องเรียนอยู่หรือไม่ ถ้าใช่ และพิมพ์ "ยกเลิก" ให้จบการร้องเรียนทันที (ไม่ไปทำรายการพัสดุ)
    if state in ['filing_desc', 'waiting_image']:
        cancel_keywords = ["ยกเลิก", "cancel", "ไม่แจ้งแล้ว", "พอแล้ว", "ออก", "exit"]
        if any(kw in text.strip().lower() for kw in cancel_keywords):
            users_col.update_one(
                {"line_user_id": uid}, 
                {"$set": {"complaint_state": "normal", "draft_desc": None}}
            )
            return "❌ ยกเลิกการแจ้งร้องเรียนเรียบร้อยค่ะ หากมีเรื่องให้ช่วยเรียกน้องบอตใหม่ได้เสมอนะคะ"
    
    # ================= AFTER-HOURS PARCEL LOGIC =================
    
    # 1. ตรวจสอบว่าผู้ใช้อยู่ในสถานะการเลือกพัสดุนอกเวลาหรือไม่
    after_hours_state = user.get('after_hours_state')
    
    if after_hours_state == 'selecting':
        try:
            # ผู้ใช้กำลังเลือกพัสดุที่ต้องการรับนอกเวลา
            pending_parcel_pins = user.get('after_hours_pending_pins', [])
            pending_parcels_data = user.get('after_hours_pending_parcels', [])
            
            text_lower = text.lower().strip()
            selected_pins = []
            
            # ตรวจสอบคำตอบแบบง่าย (สำหรับชิ้นเดียว)
            if len(pending_parcel_pins) == 1:
                simple_yes = ["ใช่", "ใช้", "รับ", "ตกลง", "ok", "yes", "ค่ะ", "ครับ", "ได้", "เอา"]
                if any(word in text_lower for word in simple_yes):
                    selected_pins = pending_parcel_pins
            
            # ถ้ายังไม่ได้เลือก ลองหาจากการตอบแบบอื่น
            if not selected_pins:
                # 1. ตรวจสอบ "ทั้งหมด" หรือ "all"
                if any(word in text_lower for word in ["ทั้งหมด", "ทั้งหมดเลย", "all", "ทุกชิ้น"]):
                    selected_pins = pending_parcel_pins
                
                # 2. ตรวจสอบตัวเลข indices (1,2,3 หรือ 1 2 3 หรือ 1-3)
                elif not selected_pins:
                    try:
                        # Parse numbers from text
                        import re
                        numbers = re.findall(r'\d+', text)
                        indices = []
                        for num_str in numbers:
                            idx = int(num_str)
                            if 1 <= idx <= len(pending_parcel_pins):
                                indices.append(idx - 1)  # Convert to 0-based
                        
                        if indices:
                            selected_pins = [pending_parcel_pins[i] for i in indices]
                    except:
                        pass
                
                # 3. ตรวจสอบว่ามี PIN หรือ tracking number ในข้อความ
                if not selected_pins and pending_parcels_data:
                    for parcel in pending_parcels_data:
                        pin = str(parcel.get('pin', ''))
                        tracking = str(parcel.get('tracking_number', ''))
                        
                        if pin in text or tracking in text:
                            selected_pins.append(pin)
            
            # ตรวจสอบว่าเลือกได้หรือไม่
            if not selected_pins:
                return (
                    f"❌ ไม่เข้าใจคำสั่งค่ะ\\n\\n"
                    f"กรุณาตอบกลับด้วย:\\n"
                    f"• ตัวเลข เช่น '1' หรือ '1,3'\\n"
                    f"• PIN เช่น '{pending_parcel_pins[0] if pending_parcel_pins else '12345'}'\\n"
                    f"• 'ทั้งหมด' สำหรับทุกชิ้น"
                )
            
            # คำนวณสถิติพัสดุ
            room_number = user.get('room_number', '-')
            total_pending_count = parcels_col.count_documents({"room_number": room_number, "status": "pending"})
            total_registered_count = len(selected_pins)
            
            # ดึงข้อมูลพัสดุที่ลงทะเบียนเต็มๆ
            registered_parcels_full = list(parcels_col.find({"pin": {"$in": selected_pins}}))
            
            # อัพเดตพัสดุที่เลือกให้เป็น after-hours
            parcels_col.update_many(
                {"pin": {"$in": selected_pins}},
                {"$set": {
                    "is_after_hours": True,
                    "after_hours_confirmed_at": datetime.datetime.now()
                }}
            )
            
            # อัพเดต user preference
            users_col.update_one(
                {"line_user_id": uid},
                {"$set": {
                    "after_hours_preference": True,
                    "after_hours_state": None,
                    "after_hours_pending_pins": None,
                    "after_hours_pending_parcels": None
                }}
            )
            
            # บันทึก Audit Log
            log_admin_action(
                action="After-Hours Registration",
                performed_by=f"User ({user.get('room_number', '-')})",
                target=f"Parcels: {', '.join(selected_pins)}",
                details=f"User confirmed {len(selected_pins)} parcel(s) for after-hours pickup"
            )
            
            # สร้าง confirmation message แบบ FlexMessage
            flex_content = create_after_hours_confirmation_flex(
                registered_parcels_full,
                total_pending_count,
                total_registered_count,
                room_number
            )
            
            # สร้างข้อความสำรอง (alt_text)
            text_reply = (
                f"✅ ลงทะเบียนรับนอกเวลาเรียบร้อยแล้วค่ะ!\n\n"
                f"📦 พัสดุที่ลงทะเบียน: {len(selected_pins)} ชิ้น\n"
                f"🕐 เวลารับนอกเวลา: 18:00-22:00 น. ที่ Lobby\n\n"
                f"ทางนิติบุคคลจะเตรียมพัสดุไว้ให้ค่ะ ขอบคุณที่แจ้งล่วงหน้านะคะ 🙏"
            )
            
            return {
                "text": text_reply,
                "flex": flex_content
            }
            
        except Exception as e:
            print(f"❌ After-Hours Selection Error: {e}")
            import traceback
            traceback.print_exc()
            # รีเซ็ตสถานะ
            users_col.update_one(
                {"line_user_id": uid},
                {"$set": {
                    "after_hours_state": None,
                    "after_hours_pending_pins": None,
                    "after_hours_pending_parcels": None
                }}
            )
            return "❌ เกิดข้อผิดพลาดค่ะ กรุณาลองใหม่อีกครั้ง"
    
    # 2. ตรวจจับความต้องการรับนอกเวลาด้วย AI
    is_ah_intent, target_pins = detect_after_hours_intent(text)
    
    if is_ah_intent:
        room_number = user.get('room_number')
        
        # ดึงพัสดุคงค้างของผู้ใช้
        pending_parcels = list(parcels_col.find({
            "room_number": room_number,
            "status": "pending"
        }).sort("timestamp", -1))
        
        if not pending_parcels:
            return (
                "ขออภัยค่ะ ตอนนี้คุณไม่มีพัสดุค้างอยู่ในระบบ 📦\n\n"
                "หากมีพัสดุมาถึงภายหลัง คุณสามารถแจ้งน้องบอตได้เลยนะคะ"
            )

        # Smart Registration: If user specified PINs/ALL
        parcels_to_register = []
        
        if target_pins:
            if target_pins == "ALL":
                parcels_to_register = pending_parcels
            else:
                for p in pending_parcels:
                    p_pin = str(p.get("pin", ""))
                    p_track = str(p.get("tracking_number", ""))
                    # Check match
                    for t in target_pins:
                        if t in p_pin or t in p_track:
                            parcels_to_register.append(p)
                            break
        
        # Case 1: Automatic Registration found
        if parcels_to_register:
             # Update to DB
            reg_pins = [p["pin"] for p in parcels_to_register]
            parcels_col.update_many(
                {"pin": {"$in": reg_pins}},
                {"$set": {
                    "is_after_hours": True,
                    "after_hours_confirmed_at": datetime.datetime.now()
                }}
            )
            users_col.update_one(
                {"line_user_id": uid},
                {"$set": {"after_hours_preference": True}}
            )
            
            # Audit Log
            log_admin_action(
                action="After-Hours Registration",
                performed_by=f"User ({room_number})",
                target=f"Parcels: {', '.join(reg_pins)}",
                details=f"Smart registration for {len(reg_pins)} items"
            )
            
            parcel_list = "\n".join([f"  • PIN {p['pin']} - {p.get('transport','-')} ({p.get('tracking_number','-')})" for p in parcels_to_register])
            text_reply = (
                f"✅ ลงทะเบียนรับนอกเวลาเรียบร้อย {len(parcels_to_register)} รายการค่ะ!\n\n"
                f"{parcel_list}\n\n"
                f"🕐 เวลารับนอกเวลา: 18:00-22:00 น. ที่ Lobby\n"
                f"ขอบคุณที่แจ้งล่วงหน้านะคะ 🙏"
            )
            return text_reply

        # Case 2: No specific PINs, ask user to select (always ask, even for single parcel)
        
        # สร้างรายการพัสดุและถามให้เลือก (แม้มีชิ้นเดียว)
        parcel_list = []
        pins = []
        for idx, p in enumerate(pending_parcels, 1):
            pin = p['pin']
            transport = p.get('transport', '-')
            tracking = p.get('tracking_number', '-')
            parcel_list.append(f"{idx}. PIN {pin} - {transport} ({tracking})")
            pins.append(pin)
        
        # บันทึกสถานะว่ากำลังรอการเลือก
        users_col.update_one(
            {"line_user_id": uid},
            {"$set": {
                "after_hours_state": "selecting",
                "after_hours_pending_pins": pins,
                "after_hours_pending_parcels": [{"pin": p['pin'], "transport": p.get('transport', '-'), "tracking_number": p.get('tracking_number', '-')} for p in pending_parcels]
            }}
        )
        
        parcel_list_str = "\n".join(parcel_list)
        
        if len(pending_parcels) == 1:
            text_reply = (
                f"คุณมีพัสดุคงค้าง 1 ชิ้น:\n\n"
                f"{parcel_list_str}\n\n"
                f"📝 ต้องการลงทะเบียนรับนอกเวลาใช่ไหมคะ?\n"
                f"(ตอบ: 'ใช่', 'รับ', 'ตกลง' หรือระบุ PIN/เลขพัสดุ)\n\n"
                f"🕐 เวลารับนอกเวลา: 18:00-22:00 น. ที่ Lobby"
            )
        else:
            text_reply = (
                f"คุณมีพัสดุคงค้าง {len(pending_parcels)} ชิ้น:\n\n"
                f"{parcel_list_str}\n\n"
                f"📝 กรุณาเลือกพัสดุที่ต้องการรับนอกเวลา\n"
                f"(ตอบ: ตัวเลข เช่น '1,3' หรือ 'ทั้งหมด' หรือระบุ PIN/เลขพัสดุ)\n\n"
                f"🕐 เวลารับนอกเวลา: 18:00-22:00 น. ที่ Lobby"
            )
        
        return text_reply


    # 3. ตรวจจับการยกเลิกรับนอกเวลา
    is_cancel, target_pins = detect_after_hours_cancel_intent(text)
    if is_cancel:
        room_number = user.get('room_number')
        
        # ดึงรายการพัสดุนอกเวลาทั้งหมดของผู้ใช้นี้ (ที่เป็น pending)
        current_ah_parcels = list(parcels_col.find({
            "room_number": room_number,
            "status": "pending",
            "is_after_hours": True
        }))
        
        if not current_ah_parcels:
            return "ไม่พบรายการพัสดุที่ลงทะเบียนรับนอกเวลาไว้ค่ะ 📦"

        # Determine which parcels to cancel
        parcels_to_cancel = []
        
        if target_pins == "ALL" or not target_pins:
            # ถ้า user ไม่ระบุ หรือบอกว่าทั้งหมด -> ยกเลิกทั้งหมด (Safe default for consistency, or ask clarification? User complained about 'cancelling all' when specific was meant. 
            # But if target_pins is empty from AI (meaning "didn't specify"), maybe we should cancel all as a fallback OR ask user. 
            # However, prompt handles specific PINs. If 'target_pins' is [], it truly implies generic "cancel".
            # BUT wait, the user said "Cancel parcel 13469 but system cancelled 2". 
            # If AI works, target_pins will have ["13469"]. 
            # So if target_pins is [], it means user said "Cancel after hours" (generic).
            parcels_to_cancel = current_ah_parcels
        else:
            # Filter by matching PINs (fuzzy match or exact?)
            # Prompt output PINs might be partial. Let's try to match.
            for p in current_ah_parcels:
                p_pin = str(p.get("pin", ""))
                p_track = str(p.get("tracking_number", ""))
                # Check if this parcel is in target_pins list (fuzzy check)
                is_match = False
                for t in target_pins:
                    if t in p_pin or t in p_track:
                        is_match = True
                        break
                if is_match:
                    parcels_to_cancel.append(p)
            
            # Safety: If AI said specific PINs but we found none, maybe just inform user.
            if not parcels_to_cancel:
                 return f"❌ ไม่พบพัสดุที่ระบุ ({', '.join(target_pins)}) ในรายการนอกเวลาของคุณค่ะ"

        if not parcels_to_cancel:
            return "❌ ไม่มีการเปลี่ยนแปลงค่ะ"

        # Update Database
        cancel_pins = [p["pin"] for p in parcels_to_cancel]
        
        parcels_col.update_many(
            {"pin": {"$in": cancel_pins}},
            {"$set": {
                "is_after_hours": False,
                "after_hours_confirmed_at": None
            }}
        )
        
        # Audit Log
        log_admin_action(
            action="After-Hours Cancellation",
            performed_by=f"User ({room_number})",
            target=f"Room: {room_number}",
            details=f"User cancelled after-hours: {', '.join(cancel_pins)}"
        )

        # Re-fetch Status for Grounded Response
        # 1. Cancelled items count
        cancelled_count = len(parcels_to_cancel)
        
        # 2. Remaining after-hours items (Query logic: pending AND is_after_hours=True)
        remaining_ah = parcels_col.count_documents({
            "room_number": room_number,
            "status": "pending",
            "is_after_hours": True
        })
        
        # 3. Message construction
        msg = f"✅ ยกเลิกรับนอกเวลาเรียบร้อย {cancelled_count} รายการค่ะ\n(PIN: {', '.join(cancel_pins)})"
        
        if remaining_ah > 0:
            msg += f"\n\n📦 ยังเหลือพัสดุรับนอกเวลาอีก {remaining_ah} รายการครับ"
        else:
            msg += f"\n\nตอนนี้ไม่มีพัสดุรับนอกเวลาค้างแล้วครับ สามารถติดต่อรับได้ในเวลาทำการปกติ"
            
        return msg

    # ================= Intent Analysis =================
    
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
            return "ได้เลยค่ะ บอตยินดีช่วยประสานงานให้นะคะ 📝 รบกวนคุณลูกค้าพิมพ์รายละเอียดปัญหาที่พบมาได้เลยค่ะ"
    
    # ================= AI Processing =================
    
    # ดึง Intent และ Context พร้อมกันเพื่อลดเวลา (Parallel)
    with ThreadPoolExecutor() as executor:
        # 1. วิเคราะห์เจตนา (พร้อม Cache)
        intent_future = executor.submit(analyze_intent, text)
        
        # 2. ดึงความรู้ (RAG) ถ้าไม่ใช่การทักทายสั้นๆ
        greeting_words = ["สวัสดี", "หวัดดี", "hello", "hi", "สวัสดีค่ะ", "สวัสดีครับ", "ดี", "ดีจ้า"]
        is_simple_greeting = text.strip().lower() in [g.lower() for g in greeting_words]
        
        rag_context = ""
        if not is_simple_greeting:
            context_future = executor.submit(get_knowledge_context, text, user)
            # ไม่ดึง rag_context ทันที รอจนกว่าจะใช้งาน
        else:
            context_future = None

        intent = intent_future.result()

    # ตรวจสอบสถานะและดำเนินการตาม intent
    # Robust cancellation handling via AI
    if intent == "CANCEL" or text.lower() in ["ยกเลิก", "cancel", "ไม่แจ้งแล้ว", "พอแล้ว"]:
        users_col.update_one(
            {"line_user_id": uid}, 
            {"$set": {"complaint_state": "normal", "draft_desc": None}}
        )
        return "❌ ยกเลิกรายการให้แล้วค่ะ หากต้องการแจ้งเรื่องใหม่ทักน้องบอตได้เสมอนะคะ"

    # COMPLAINT Logic: จัดการตามความละเอียดของข้อความ
    if intent in ["COMPLAINT_START", "COMPLAINT_DETAIL"]:
        if state == 'normal':
            if intent == "COMPLAINT_START":
                users_col.update_one({"line_user_id": uid}, {"$set": {"complaint_state": "filing_desc"}})
                return "รับทราบค่ะคุณลูกค้า บอตพร้อมช่วยดูแลนะคะ 📝 รบกวนคุณลูกค้าพิมพ์รายละเอียดปัญหาที่พบมาได้เลยค่ะ"
            else:
                # COMPLAINT_DETAIL: มีข้อมูลแล้ว บันทึกและขอรูปทันที
                users_col.update_one(
                    {"line_user_id": uid}, 
                    {"$set": {"complaint_state": "waiting_image", "draft_desc": text}}
                )
                return f"รับทราบปัญหา '{text}...' ค่ะ น้องบอตบันทึกข้อมูลไว้แล้ว 📝\n\n📸 เพื่อให้ช่างตรวจสอบได้ตรงจุด รบกวนคุณลูกค้าถ่ายรูปหน้างานส่งมาให้น้องบอตหน่อยนะคะ"

    if state == 'filing_desc':
        users_col.update_one(
            {"line_user_id": uid}, 
            {"$set": {"complaint_state": "waiting_image", "draft_desc": text}}
        )
        return f"ขอบคุณสำหรับรายละเอียดค่ะ น้องบอตบันทึกเรื่อง '{text[:50]}' ไว้แล้วนะคะ 📝\n\n📸 อีกนิดเดียวนะคะ รบกวนส่งรูปภาพประกอบมาให้หน่อยค่ะ พี่ๆ นิติฯ จะได้เข้าตรวจสอบได้ถูกจุดค่ะ"

    if state == 'waiting_image':
        return "📸 น้องบอทยังรอรูปภาพประกอบอยู่นะคะ หรือถ้าต้องการยกเลิก สามารถพิมพ์ว่า 'ยกเลิก' ได้เลยค่ะ"

    # ตรวจสอบ RAG Context ที่ดึงมาแบบ Parallel
    if context_future:
        rag_result = context_future.result()
        context_msg = f"\n[Context]:\n{rag_result}\n" if rag_result else ""
    else:
        # สำหรับคำทักทาย ใช้ข้อมูลส่วนตัวเบื้องต้น
        context_msg = f"\n[Context]:\nผู้ใช้งาน: {user.get('first_name', 'ลูกบ้าน')} {user.get('last_name', '')} (ห้อง {user.get('room_number', 'ไม่ระบุ')})\n"
    
    history = get_gemini_chat_history(uid)
    try:
        chat = client.chats.create(
            model='gemini-3-flash-preview',
            config=types.GenerateContentConfig(system_instruction=CHAT_SYSTEM_PROMPT),
            history=history
        )
        res = chat.send_message(f"{text}\n{context_msg}")
        return res.text.strip() # Handler will auto-wrap this in Text Flex
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
        
        update_chat_history(uid, 'user', event.message.text, platform="line")
        reply_data = process_text_logic(user, event.message.text)
        
        reply_text = ""
        flex_contents = None
        
        if isinstance(reply_data, dict):
            reply_text = reply_data.get('text', '')
            flex_contents = reply_data.get('flex')
        else:
            reply_text = str(reply_data)
            # Auto-wrap simple text in Flex Bubble for premium look?
            # Yes, as requested "รูปแบบสวยๆ"
            if len(reply_text) < 500: # Limit length for bubble
                flex_contents = create_text_flex(reply_text)
        
        update_chat_history(uid, 'model', reply_text, platform="line")
        
        # Use helper to send (supports Flex) (pass flex_contents)
        if flex_contents:
             send_line_message(uid, message=reply_text, flex_contents=flex_contents)
        else:
             line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply_text)]))

# ================= Handle Image Message =================

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

                    # ปรับปรุง Vision Prompt ให้ละเอียดขึ้น
                    vision_prompt = (
                        f"คำอธิบายจากลูกบ้าน: '{user_desc}'\n\n"
                        
                        "📋 วิเคราะห์รูปภาพนี้ประกอบกับคำอธิบายข้างต้น:\n\n"
                        
                        "เกณฑ์ความสำคัญ:\n"
                        "🔴 HIGH (ต้องแก้ไขภายในวันนี้):\n"
                        "   • ไฟไหม้ ไฟฟ้าลัดวงจร ไฟช็อต\n"
                        "   • ไฟดับทั้งหมด ไฟดับทั้งอาคาร ไฟดับพื้นที่กว้าง\n"
                        "   • เสาไฟล้ม เสาไฟโค่น อุปกรณ์ไฟฟ้าหลักเสียหาย\n"
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
                        
                        "หน้าที่:\n"
                        "1. วิเคราะห์รูปภาพประกอบกับคำอธิบาย สรุปปัญหาเชิงเทคนิค\n"
                        "2. วิเคราะห์ภาพรวมของรูปภาพ (สภาพแวดล้อม ความเสียหายรอบๆ)\n"
                        "3. สรุปผลการวิเคราะห์ทั้งสองส่วนรวมกัน **อย่างกระชับ**\n\n"
                        "Format ตอบ: 'Summary || Urgency || Detailed_Analysis'\n"
                        "- Summary: สรุปปัญหาสั้นๆ (ไม่เกิน 80 ตัวอักษร)\n"
                        "- Urgency: ประเมินความเร่งด่วน (High, Medium, Low) ตามเกณฑ์ด้านบนอย่างเคร่งครัด\n"
                        "- Detailed_Analysis: แสดงผลการวิเคราะห์แบบกระชับ แบ่งเป็น 2 หัวข้อหลัก:\n"
                        "  • วิเคราะห์ตามรายละเอียดและรูปภาพ: [เนื้อหากระชับ]\n"
                        "  • วิเคราะห์ภาพรวมของรูปภาพ: [เนื้อหากระชับ]\n"
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
                            # ปรับปรุงรูปแบบการแสดงผลตามที่ต้องการ
                            final_ai_summary = (
                                f"{ai_summary_text}\n\n"
                                f"🤖 วิเคราะห์เชิงลึก:\n"
                                f"{detailed_analysis}"
                            )
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
                
                # 7. ตอบกลับผู้ใช้
                success_msg = (
                    f"✅ รับแจ้งร้องเรียนเรียบร้อยแล้วค่ะ!\n\n"
                    f"📌 เรื่อง: {user_desc}\n"
                    f"📷 ได้รับรูปภาพแล้ว\n"
                    f"เจ้าหน้าที่จะรีบดำเนินการตรวจสอบให้นะคะ ขอบคุณค่ะ 🙏"
                )
                
                update_chat_history(uid, 'model', success_msg, platform="line")
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

# Helper for consistent datetime formatting (ISO 8601 UTC)
def format_datetime(dt):
    """
    Format datetime to Thai-friendly readable format: DD/MM/YYYY HH:MM
    """
    if not dt:
        return "-"
    try:
        # Convert to Bangkok timezone
        bkk_tz = pytz.timezone('Asia/Bangkok')
        if dt.tzinfo is None:
            # Assume UTC if no timezone info
            dt = pytz.utc.localize(dt)
        bkk_time = dt.astimezone(bkk_tz)
        return bkk_time.strftime("%d/%m/%Y %H:%M")
    except Exception as e:
        print(f"⚠️ Datetime format error: {e}")
        return "-"

@app.route('/api/dashboard', methods=['GET'])
@require_api_token
def get_dashboard_stats():
    """ดึงข้อมูลสถิติทั้งหมดสำหรับแดชบอร์ด"""
    print(f"DEBUG: Dashboard requested by {request.remote_addr}")
    print(f"DEBUG: Headers: {dict(request.headers)}")
    try:
        # Use ThreadPoolExecutor to run queries in parallel
        with ThreadPoolExecutor() as executor:
            # Submit all queries
            f_users = executor.submit(users_col.count_documents, {})
            f_total_complaints = executor.submit(complaints_col.count_documents, {})
            f_resolved_complaints = executor.submit(complaints_col.count_documents, {"status": "resolved"})
            f_pending_complaints = executor.submit(complaints_col.count_documents, {"status": "pending"})
            f_high = executor.submit(complaints_col.count_documents, {"priority": "high", "status": "pending"})
            f_medium = executor.submit(complaints_col.count_documents, {"priority": "medium", "status": "pending"})
            f_low = executor.submit(complaints_col.count_documents, {"priority": "low", "status": "pending"})
            f_total_parcels = executor.submit(parcels_col.count_documents, {})
            f_picked_up = executor.submit(parcels_col.count_documents, {"status": "picked_up"})
            f_pending_parcels = executor.submit(parcels_col.count_documents, {"status": "pending"})

            # Get results (this will wait for the slowest query, but they run simultaneously)
            return jsonify({
                "users": f_users.result(),
                "total_complaints": f_total_complaints.result(),
                "resolved_complaints": f_resolved_complaints.result(),
                "pending_complaints": f_pending_complaints.result(),
                "pending_high": f_high.result(),
                "pending_medium": f_medium.result(),
                "pending_low": f_low.result(),
                "total_parcels": f_total_parcels.result(),
                "picked_up_parcels": f_picked_up.result(),
                "pending_parcels": f_pending_parcels.result()
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
        # Use ThreadPoolExecutor to run queries in parallel
        with ThreadPoolExecutor() as executor:
            f_recent_parcels = executor.submit(lambda: list(parcels_col.find().sort("timestamp", -1).limit(3)))
            f_recent_complaints = executor.submit(lambda: list(complaints_col.find().sort("timestamp", -1).limit(3)))
            
            recent_parcels = f_recent_parcels.result()
            recent_complaints = f_recent_complaints.result()
        
        activities = []
        
        for parcel in recent_parcels:
            activities.append({
                "type": "parcel",
                "message": f"พัสดุใหม่: ห้อง {parcel.get('room_number', '-')}",
                "details": f"{parcel.get('transport', '-')} - {parcel.get('recipient_name', '-')}",
                "timestamp": format_datetime(parcel.get('timestamp'))
            })
        
        # [OPTIMIZATION] Batch fetch users for complaints in activity
        complaint_user_ids = list(set(c.get("line_user_id") for c in recent_complaints if c.get("line_user_id")))
        c_users_map = {}
        if complaint_user_ids:
            c_users_list = list(users_col.find({"line_user_id": {"$in": complaint_user_ids}}, {"line_user_id": 1, "display_name": 1}))
            c_users_map = {u["line_user_id"]: u for u in c_users_list}
        
        for complaint in recent_complaints:
            user_id = complaint.get("line_user_id")
            user = c_users_map.get(user_id)
            activities.append({
                "type": "complaint",
                "message": f"แจ้งร้องเรียน: ห้อง {complaint.get('room_number', '-')}",
                "details": f"{complaint.get('description', '-')[:30]}...",
                "timestamp": format_datetime(complaint.get('timestamp'))
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
                "timestamp": format_datetime(parcel.get('timestamp'))
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
        # print(f"DEBUG: Users requested by {request.remote_addr}")
        # Use projection to fetch only necessary fields
        users = list(users_col.find({}, {
            "room_number": 1, 
            "first_name": 1, 
            "last_name": 1, 
            "display_name": 1, 
            "phone_number": 1, 
            "platform": 1, 
            "line_user_id": 1,
            "last_active": 1, 
            "_id": 0
        }).sort("last_active", -1).limit(100))
        # print(f"DEBUG: Found {len(users)} users in DB")
        
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
            platform = u.get("platform")
            if not platform:
                platform = "LINE" if u.get("line_user_id") else "Web/App"
            
            # Format เวลาใช้งานล่าสุด
            last_active = u.get("last_active")
            last_active_str = format_datetime(last_active)
            
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
        
        return jsonify({"items": result})
        
    except Exception as e:
        print(f"Error getting users: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= Complaints API =================

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
            
        items = list(complaints_col.find(query, {
            "room_number": 1,
            "description": 1,
            "ai_summary": 1,
            "status": 1,
            "priority": 1,
            "timestamp": 1,
            "image_url": 1,
            "line_user_id": 1,
            "urgency_level": 1
        }).limit(100))
        
        # Sorting Logic
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
                "timestamp": format_datetime(c.get("timestamp")),
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
            
        items = list(parcels_col.find(query, {
            "room_number": 1, "recipient_name": 1, "pin": 1, "transport": 1, "courier": 1,
            "tracking_number": 1, "image_url": 1, "timestamp": 1, "is_after_hours": 1
        }).sort("timestamp", -1).limit(200))
        result = []
        for i in items:
            result.append({
                "id": str(i['_id']),
                "room_number": i.get("room_number", "-"),
                "recipient_name": i.get("recipient_name", "-"),
                "pin": i.get("pin", "-"),
                "courier": i.get("transport", "-") or i.get("courier", "-"),
                "tracking_number": i.get("tracking_number", "-"),
                "image_url": i.get("image_url", ""),
                "timestamp": format_datetime(i.get('timestamp')),
                "is_after_hours": i.get("is_after_hours", False)
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
            last_active_str = format_datetime(last_active)
            
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
        
        return jsonify({"items": result})
        
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
        
        # [OPTIMIZATION] ใช้ projection และ limit เพื่อความเร็ว
        items = list(parcels_col.find(query, {
            "room_number": 1,
            "recipient_name": 1,
            "pin": 1,
            "transport": 1,
            "tracking_number": 1,
            "image_url": 1,
            "timestamp": 1,
            "is_after_hours": 1,
            "after_hours_confirmed_at": 1,
            "_id": 1
        }).sort("timestamp", -1).limit(200)) # จำกัด 200 รายการล่าสุดเพื่อความเร็ว
        
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
                "timestamp": format_datetime(i.get('timestamp')),
                "is_after_hours": i.get("is_after_hours", False)
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
        }).sort("timestamp", -1).limit(100))
        
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

        # [OPTIMIZATION] Batch fetch users to avoids N+1 query
        user_ids = list(set(c.get("line_user_id") for c in items if c.get("line_user_id")))
        users_map = {}
        if user_ids:
            users_list = list(users_col.find({"line_user_id": {"$in": user_ids}}, {"line_user_id": 1, "display_name": 1}))
            users_map = {u["line_user_id"]: u for u in users_list}

        result = []
        for c in items:
            user_id = c.get("line_user_id")
            user = users_map.get(user_id)
            
            result.append({
                "id": str(c.get('_id')),
                "room_number": c.get("room_number", "-"),
                "description": c.get("description", "-"),
                "summary": c.get("ai_summary", "-"),
                "status": c.get("status", "pending"),
                "priority": c.get("priority", "medium"),
                "timestamp": format_datetime(c.get("timestamp")),
                "image_url": c.get("image_url", ""),
                "display_name": user.get("display_name", "-") if user else "-",
                "urgency_level": c.get("urgency_level", "Medium")
            })
        return jsonify({"items": result})
    except Exception as e:
        print(f"Complaints search error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def notify_user_platform_agnostic(user, message, image_url=None, update_history=True, flex_contents=None):
    """
    ส่งแจ้งเตือนให้ผู้ใช้ตาม Platform (LINE/Web)
    รองรับ Flex Message
    """
    try:
        if not user: return False
        
        uid = user.get("line_user_id")
        platform = user.get("platform", "line")
        
        # 1. Update Chat History
        if update_history:
            # บันทึกประวัติการสนทนา
            update_chat_history(uid, 'model', message, platform=platform, image_url=image_url)
            
        # 2. Send Message
        if platform == "line" and uid:
            # Use send_line_message which now supports flex
            send_line_message(uid, message=message, image_url=image_url, flex_contents=flex_contents)
            return True
            
        elif platform == "web":
            # สำหรับ Web: Chat History ถูกอัพเดตแล้ว Client จะดึงไปแสดงเอง
            # (อนาคตอาจเพิ่ม WebSocket push)
            return True
            
        return False
    except Exception as e:
        print(f"❌ Notify User Error: {e}")
        return False

# ================= SCAN PARCEL API (ENHANCED) =================

@app.route('/api/scan', methods=['POST'])
@require_api_token
def scan_parcel_api():
    # API สำหรับ Frontend Upload ภาพพัสดุ -> ให้ Gemini อ่าน
    if 'image' not in request.files:
        return jsonify({"status": "error", "message": "No image uploaded"}), 400

    file = request.files['image']
    
    # Validate Image
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

def send_notification_async(user_id, message, image_url=None, flex_contents=None):
    """ส่ง LINE Async เพื่อไม่ให้บล็อคการทำงานหลัก - รองรับ FlexMessage"""
    try:
        executor.submit(send_line_message, user_id, message, image_url, flex_contents)
    except Exception as e:
        print(f"Async Notification Error: {e}")



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
        
        # 6. นับพัสดุคงค้างใหม่ (Move up to use in message)
        parcel_count = 0
        room = data.get("room_number")
        if room and room != "-":
            parcel_count = parcels_col.count_documents({"room_number": room, "status": "pending"})

        # 7. สร้าง FlexMessage Carousel สำหรับพัสดุใหม่
        # สร้างข้อความสำรอง (alt_text) สำหรับกรณีที่ Flex ไม่แสดงผล
        message = (
            f"📦 มีพัสดุมาใหม่ค่ะ!\n\n"
            f"🏠 ห้อง: {data.get('room_number', '-')}\n"
            f"🚚 ขนส่ง: {data.get('transport', data.get('courier', '-'))}\n"
            f"📦 Tracking: {data.get('tracking_number', '-')}\n"
            f"🔑 PIN: {pin}\n\n"
            f"📦 รวมพัสดุค้างทั้งหมด: {parcel_count} ชิ้น\n"
            f"(กรุณาแจ้ง PIN และรับของได้ที่นิติบุคคลค่ะ)\n\n"
            f"ℹ️ กรณีผู้ใช้มารับนอกเวลา (18:00-22:00 น.)\n"
            f"กรุณาแจ้งน้องบอทด้วยนะคะ"
        )

        image_url = data.get("image_url")
        
        # สร้าง FlexMessage Carousel สำหรับพัสดุที่เพิ่งสร้าง
        parcel_data = {
            "pin": pin,
            "transport": data.get('transport', data.get('courier', '-')),
            "tracking_number": data.get('tracking_number', '-'),
            "room_number": data.get('room_number', '-'),
            "recipient_name": data.get('recipient_name', '-'),
            "image_url": image_url
        }
        flex_content = create_parcel_carousel([parcel_data])

        # 8. ส่งแจ้งเตือน (พหุแพลตฟอร์ม: LINE + Web) -- [SPEED OPTIMIZATION] Async
        # Note: image_url is embedded in flex_content, no need to send separately
        if user:
            executor.submit(notify_user_platform_agnostic, user, message, None, True, flex_content)


        notification_lines = []
        notification_lines.append(f"✅ ส่งแจ้งเตือนถึง: {user.get('display_name', 'Unknown')} (ห้อง {user.get('room_number', '-')})")
        
        return jsonify({
            "status": "saved",
            "message": "บันทึกพัสดุสำเร็จ",
            "pin": pin,
            "parcel_count": parcel_count,
            "sent": True,
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
        update_result = parcels_col.update_one(
            {"_id": parcel["_id"]},
            {"$set": {"status": "picked_up", "pickup_time": datetime.datetime.now()}}
        )
        
        print(f"📦 [Pickup] PIN {pin}: Matched {update_result.matched_count}, Modified {update_result.modified_count}")

        # Verify Update
        if update_result.modified_count == 0:
             # Try fetching again to see status
             check_p = parcels_col.find_one({"_id": parcel["_id"]})
             print(f"⚠️ [Pickup Warning] DB Not Modified. Current Status: {check_p.get('status')}")
             if check_p and check_p.get('status') == 'picked_up':
                 pass # Already picked up?
             else:
                 return jsonify({"status": "error", "message": "Failed to update parcel status"}), 500
        
        # 3. บันทึก Audit Log (เปลี่ยนชื่อให้ตรงกับความต้องการของ user)
        log_admin_action(
            action="กดรับของ",
            performed_by=admin_name,
            target=f"Room: {parcel.get('room_number', '-')}, PIN: {pin}",
            details=f"Tracking: {parcel.get('tracking_number', '-')}, Courier: {parcel.get('transport', '-')}"
        )
        
        # 4. ค้นหาผู้ใช้จากห้อง
        user = users_col.find_one({"room_number": parcel.get("room_number")})
        
        # 5. ส่งแจ้งเตือนการรับพัสดุ (ส่งทุกกรณี ตาม Request ล่าสุด)
        is_after_hours = parcel.get("is_after_hours", False)
        
        if user:
            # Construct message for pickup
            message = (
                f"✅ พัสดุของคุณถูกรับแล้ว!\n\n"
                f"📦 พัสดุ: {parcel.get('tracking_number', '-')}\n"
                f"🏠 ห้อง: {parcel.get('room_number', '-')}\n"
                f"🚚 ขนส่ง: {parcel.get('transport', '-')}\n"
                f"🔑 PIN: {parcel.get('pin', '-')}\n"
                f"⏰ เวลารับ: {format_datetime(datetime.datetime.now())}\n"
            )
            
            if is_after_hours:
                message += f"(รายการลงทะเบียนรับนอกเวลา)\n"
                
            message += f"\nขอบคุณที่ใช้บริการค่ะ"
            
            # สร้าง Flex Message สำหรับการรับพัสดุ
            # Note: image_url is embedded in flex_content, no need to send separately
            room = parcel.get('room_number', '-')
            flex_content = create_parcel_pickup_flex(parcel, room)
            
            executor.submit(notify_user_platform_agnostic, user, message, None, True, flex_content)
            print(f"📤 [Pickup] Notification sent to {user.get('display_name')}")
        else:
            print(f"ℹ️ [Pickup] User not found for room {parcel.get('room_number')}, skip notification")
        
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
        
        # 5. ฟังก์ชันย่อยสำหรับประมวลผลรูปภาพและส่งแจ้งเตือน (Async เพื่อความเร็ว)
        def background_resolve_tasks(complaint_obj, admin_note, temp_image_path, user_obj):
            try:
                img_url = None
                if temp_image_path and os.path.exists(temp_image_path):
                    try:
                        up_res = cloudinary.uploader.upload(
                            temp_image_path,
                            folder="complaints_resolved",
                            tags=["complaint_resolved", f"complaint:{str(complaint_obj['_id'])}"]
                        )
                        img_url = up_res.get('secure_url')
                        complaints_col.update_one(
                            {"_id": complaint_obj["_id"]},
                            {"$set": {"resolved_image_url": img_url}}
                        )
                        print(f"✅ Background Image Upload Success: {img_url}")
                    except Exception as e:
                        print(f"❌ Background Upload Error: {e}")
                    finally:
                        if os.path.exists(temp_image_path): os.remove(temp_image_path)
                
                # สร้างข้อความแจ้งเตือน
                message = (
                    f"✅ การร้องเรียนของคุณได้รับการแก้ไขแล้ว!\n\n"
                    f"📌 เรื่อง: {complaint_obj.get('description', '')}\n"
                    f"🏠 ห้อง: {complaint_obj.get('room_number', '-')}\n"
                    f"📅 วันที่แจ้ง: {complaint_obj.get('timestamp', '').strftime('%d/%m/%Y') if complaint_obj.get('timestamp') else '-'}\n"
                    f"✅ ดำเนินการเสร็จ: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
                )
                if admin_note:
                    message += f"\n📝 หมายเหตุ: {admin_note}"
                message += "\n\nขอบคุณที่แจ้งปัญหาค่ะ 🙏"
                
                # สร้าง Flex Message
                flex_content = create_complaint_update_flex(
                    status="resolved",
                    description=complaint_obj.get('description', ''),
                    room=complaint_obj.get('room_number', '-'),
                    message=message,
                    image_url=img_url
                )
                
                # ส่งแจ้งเตือน (พหุแพลตฟอร์ม)
                notify_user_platform_agnostic(user_obj, message, img_url, update_history=True, flex_contents=flex_content)
                print(f"✅ Background Notification Sent to: {user_obj.get('line_user_id') if user_obj else 'Unknown'}")
                
            except Exception as e:
                print(f"❌ Critical Error in background_resolve_tasks: {e}")
                import traceback
                traceback.print_exc()

        # 6. ค้นหาผู้ใช้
        user = users_col.find_one({"line_user_id": complaint.get("line_user_id")})
        
        # 7. จัดการรูปภาพใน Main Thread ป้องกัน context issues
        temp_path = None
        if 'image' in request.files and request.files['image'].filename != '':
            image_file = request.files['image']
            is_valid, _ = validate_image(image_file)
            if is_valid:
                suffix = f".{image_file.filename.rsplit('.', 1)[1].lower()}" if '.' in image_file.filename else '.jpg'
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
                    image_file.save(tf.name)
                    temp_path = tf.name
        
        # 8. [SPEED OPTIMIZATION] ทำงานส่วนที่เหลือในพื้นหลังทั้งหมด
        executor.submit(background_resolve_tasks, complaint, resolved_note, temp_path, user)
        
        return jsonify({
            "status": "success",
            "message": "บันทึกสถานะเรียบร้อยแล้ว (กำลังส่งแจ้งเตือนในพื้นหลัง)"
        })
        
    except Exception as e:
        print(f"❌ Resolve Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ================= AUDIT LOGS ENDPOINT =================

@app.route('/api/admin/audit-logs', methods=['GET'])
@require_api_token
def get_audit_logs():
    """ดึง Audit Logs ล่าสุด"""
    try:
        # ดึง logs ล่าสุด 30 รายการ (เรียงจากใหม่ไปเก่า) ตามคำขอของ user
        # ใช้ projection เลือกเฉพาะ field ที่จำเป็น
        # Force strict limit and ensure index exists
        try:
            audit_logs_col.create_index([("timestamp", -1)]) 
        except: 
            pass
            
        logs = list(audit_logs_col.find({}, {
            "action": 1,
            "performed_by": 1,
            "target": 1,
            "timestamp": 1,
            "details": 1,
            "_id": 0
        }).sort("timestamp", -1).limit(20))  # แสดง 20 รายการล่าสุด
        
        result = []
        for log in logs:
            result.append({
                "action": log.get("action", ""),
                "performed_by": log.get("performed_by", ""),
                "target": log.get("target", ""),
                "timestamp": format_datetime(log.get("timestamp")),
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
            'PIN', 'สถานะ', 'ประเภทการรับ', 'วันที่รับเข้า', 'วันที่รับออก', 
            'รูปภาพ URL', 'หมายเหตุ'
        ])
        
        # เขียนข้อมูล
        for parcel in parcels:
            pickup_type = "รับนอกเวลา" if parcel.get('is_after_hours') else "รับในเวลา"
            writer.writerow([
                str(parcel.get('_id', '')),
                parcel.get('room_number', ''),
                parcel.get('recipient_name', ''),
                parcel.get('transport', ''),
                parcel.get('tracking_number', ''),
                # แปลง PIN เป็นตัวเลขเพื่อให้ Excel ไม่มองเป็น string ถ้าต้องการ (แต่ PIN 5 หลัก เก็บเป็น string ปลอดภัยกว่าเรื่อง 0 นำหน้า)
                parcel.get('pin', ''), 
                parcel.get('status', ''),
                pickup_type,
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

# ================= AFTER-HOURS PARCELS API =================

@app.route('/api/parcels/after-hours', methods=['GET'])
@require_api_token
def get_after_hours_parcels():
    """ดึงรายการพัสดุที่ลงทะเบียนรับนอกเวลาทั้งหมด"""
    try:
        # ดึงพัสดุที่ is_after_hours = true และ status = pending
        parcels = list(parcels_col.find({
            "is_after_hours": True,
            "status": "pending"
        }).sort("after_hours_confirmed_at", -1))
        
        result = []
        for p in parcels:
            result.append({
                "id": str(p.get('_id')),
                "room_number": p.get("room_number", "-"),
                "recipient_name": p.get("recipient_name", "-"),
                "pin": p.get("pin", "-"),
                "transport": p.get("transport", "-"),
                "tracking_number": p.get("tracking_number", "-"),
                "image_url": p.get("image_url", ""),
                "confirmed_at": format_datetime(p.get("after_hours_confirmed_at")),
                "timestamp": format_datetime(p.get("timestamp"))
            })
        
        return jsonify({"items": result})
        
    except Exception as e:
        print(f"After-Hours Parcels API Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/parcels/after-hours/export', methods=['GET'])
@require_api_token
def export_after_hours_parcels():
    """Export พัสดุนอกเวลาเป็น CSV/XLSX"""
    try:
        # ดึงพัสดุนอกเวลาทั้งหมด (รวมทั้งที่รับแล้ว)
        parcels = list(parcels_col.find({
            "is_after_hours": True
        }))
        
        # เรียงลำดับตาม PIN (แปลงเป็น int ก่อนเรียง)
        # ถ้า PIN ไม่ใช่ตัวเลข จะเอาไว้ท้ายสุด
        def get_pin_sort_key(parcel):
            pin = parcel.get('pin', '99999')
            try:
                return int(pin)
            except (ValueError, TypeError):
                return 99999
        
        parcels.sort(key=get_pin_sort_key)
        
        # สร้าง CSV ใน memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # เขียน header
        writer.writerow([
            'ห้อง', 'ชื่อผู้รับ', 'บริษัทขนส่ง', 'เลขพัสดุ',
            'PIN', 'สถานะ', 'วันที่ยืนยันรับนอกเวลา', 'วันที่รับเข้า', 
            'วันที่รับออก', 'รูปภาพ URL', 'ช่องเซ็นชื่อ'
        ])
        
        # เขียนข้อมูล
        for parcel in parcels:
            writer.writerow([
                parcel.get('room_number', ''),
                parcel.get('recipient_name', ''),
                parcel.get('transport', ''),
                parcel.get('tracking_number', ''),
                parcel.get('pin', ''),
                parcel.get('status', ''),
                parcel.get('after_hours_confirmed_at', '').strftime('%Y-%m-%d %H:%M:%S') if parcel.get('after_hours_confirmed_at') else '',
                parcel.get('timestamp', '').strftime('%Y-%m-%d %H:%M:%S') if parcel.get('timestamp') else '',
                parcel.get('pickup_time', '').strftime('%Y-%m-%d %H:%M:%S') if parcel.get('pickup_time') else '',
                parcel.get('image_url', ''),
                '________________' # ช่องเซ็นชื่อ
            ])
        
        # สร้าง response
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=after_hours_parcels_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "Content-Type": "text/csv; charset=utf-8-sig"  # UTF-8 BOM for Excel compatibility
            }
        )
        
    except Exception as e:
        print(f"Export After-Hours Parcels Error: {e}")
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

# ================= AUTO-CLEANUP OLD DATA =================

def cleanup_old_resolved_complaints():
    """
    ลบร้องเรียนที่ status='resolved' และเก่ากว่า 90 วัน
    """
    try:
        ninety_days_ago = datetime.datetime.now() - datetime.timedelta(days=90)
        
        # ค้นหาและลบ
        result = complaints_col.delete_many({
            "status": "resolved",
            "timestamp": {"$lt": ninety_days_ago}
        })
        
        deleted_count = result.deleted_count
        print(f"🗑️  Deleted {deleted_count} old resolved complaints")
        
        # บันทึก audit log
        if deleted_count > 0:
            audit_logs_col.insert_one({
                "action": "Auto Cleanup - Complaints",
                "performed_by": "system",
                "target": f"{deleted_count} complaints",
                "details": f"Deleted {deleted_count} resolved complaints older than 90 days",
                "timestamp": get_bkk_now()
            })
        
        return deleted_count
    except Exception as e:
        print(f"❌ Cleanup complaints error: {e}")
        return 0

def cleanup_old_picked_parcels():
    """
    ลบพัสดุที่ status='pickedup' และเก่ากว่า 90 วัน
    """
    try:
        ninety_days_ago = datetime.datetime.now() - datetime.timedelta(days=90)
        
        # ค้นหาพัสดุที่จะลบ
        old_parcels = list(parcels_col.find({
            "status": "pickedup",
            "pickup_time": {"$lt": ninety_days_ago}
        }))
        
        if len(old_parcels) == 0:
            print("✅ No old parcels to cleanup")
            return 0
            
        # ลบรูปจาก Cloudinary
        for parcel in old_parcels:
            try:
                image_url = parcel.get("image_url")
                if image_url and "cloudinary.com" in image_url:
                    parts = image_url.split("/")
                    if len(parts) > 0:
                        filename = parts[-1].split(".")[0]
                        folder = parts[-2] if len(parts) > 1 else ""
                        public_id = f"{folder}/{filename}" if folder else filename
                        cloudinary.uploader.destroy(public_id)
                        print(f"🗑️  Deleted cloud image: {public_id}")
            except Exception as e:
                print(f"Error deleting parcel image: {e}")
        
        # ลบจากฐานข้อมูล
        result = parcels_col.delete_many({
            "status": "pickedup",
            "pickup_time": {"$lt": ninety_days_ago}
        })
        
        deleted_count = result.deleted_count
        print(f"🗑️  Deleted {deleted_count} old picked parcels")
        
        # บันทึก audit log
        if deleted_count > 0:
            audit_logs_col.insert_one({
                "action": "Auto Cleanup - Parcels",
                "performed_by": "system",
                "target": f"{deleted_count} parcels",
                "details": f"Deleted {deleted_count} picked parcels older than 90 days",
                "timestamp": get_bkk_now()
            })
        
        return deleted_count
    except Exception as e:
        print(f"❌ Cleanup parcels error: {e}")
        return 0

def cleanup_old_audit_logs():
    """
    ลบ audit logs ที่เก่ากว่า 90 วัน
    """
    try:
        ninety_days_ago = datetime.datetime.now() - datetime.timedelta(days=90)
        
        # ค้นหาและลบ
        result = audit_logs_col.delete_many({
            "timestamp": {"$lt": ninety_days_ago}
        })
        
        deleted_count = result.deleted_count
        print(f"🗑️  Deleted {deleted_count} old audit logs")
        
        return deleted_count
    except Exception as e:
        print(f"❌ Cleanup audit logs error: {e}")
        return 0

@app.route('/api/admin/cleanup-old-data', methods=['POST'])
@require_api_token
def api_cleanup_old_data():
    """
    API สำหรับลบข้อมูลเก่าอัตโนมัติ (ควรเรียกจาก cron job)
    - ลบร้องเรียนที่ปิดงานแล้ว (resolved) มากกว่า 90 วัน
    - ลบพัสดุที่รับแล้ว (pickedup) มากกว่า 90 วัน
    """
    try:
        print("\n🔄 Starting auto-cleanup process...")
        
        complaints_deleted = cleanup_old_resolved_complaints()
        parcels_deleted = cleanup_old_picked_parcels()
        audit_logs_deleted = cleanup_old_audit_logs()
        
        total_deleted = complaints_deleted + parcels_deleted + audit_logs_deleted
        
        print(f"✅ Cleanup completed: {total_deleted} items deleted\n")
        
        return jsonify({
            "status": "success",
            "message": "Cleanup completed successfully",
            "deleted": {
                "complaints": complaints_deleted,
                "parcels": parcels_deleted,
                "audit_logs": audit_logs_deleted,
                "total": total_deleted
            },
            "timestamp": get_bkk_now().isoformat()
        })
    except Exception as e:
        print(f"❌ Cleanup API error: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# ================= WEB CHAT API =================

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
                    # ตรวจสอบนามสกุลจาก image_type
                    if image_type.lower() not in ALLOWED_EXTENSIONS:
                        return jsonify({"error": f"นามสกุลไฟล์ .{image_type} ไม่รองรับ"}), 400

                    # ถอดรหัส base64
                    image_data = base64.b64decode(image_base64)
                    
                    # ตรวจสอบขนาดข้อมูลหลังถอดรหัส
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
                # กรณีส่งรูปมาแต่ไม่ได้อยู่ในสถานะรอรูป
                reply_msg = "ได้รับรูปแล้วค่ะ 📸 (ไม่ได้อยู่ในโหมดแจ้งร้องเรียน)\nหากต้องการแจ้งร้องเรียน กรุณาพิมพ์รายละเอียดเข้ามาก่อนนะคะ"
                
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
        
        # ประมวลผลข้อความผ่าน Logic กลาง (เหมือน LINE)
        update_chat_history(uid, 'user', msg, platform="web")
        reply_data = process_text_logic(user, msg)
        
        # Handle dict response (Flex)
        if isinstance(reply_data, dict):
            reply_text = reply_data.get('text', '')
            # Web might not support flex, just use text
        else:
            reply_text = str(reply_data)
            
        ts = update_chat_history(uid, 'model', reply_text, platform="web")
        
        # [REDUNDANCY REMOVED] update_chat_history now handles save_full_chat_history automatically

        return jsonify({
            "reply": reply_text, 
            "status": "success",
            "timestamp": ts.isoformat() if ts else datetime.datetime.utcnow().isoformat(),
            "is_registered": is_registered(user)
        })

    except Exception as e:
        print(f"Web API Error: {e}")
        return jsonify({"error": str(e)}), 500

def process_web_complaint_image(user, image_path):
    """
    ประมวลผลรูปภาพการแจ้งร้องเรียนจากเว็บ
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
                f"⚠️ **สำคัญ**: วิเคราะห์รูปภาพเป็นหลัก (น้ำหนัก 80%) และใช้คำอธิบายจากผู้ใช้เป็นบริบทเสริม (น้ำหนัก 20%) เท่านั้น\n\n"
                f"คำอธิบายจากลูกบ้าน (บริบทเสริม): '{user_desc}'\n\n"
                
                "📋 **วิเคราะห์รูปภาพนี้เป็นหลัก**:\n"
                "ให้ความสำคัญกับสิ่งที่คุณเห็นในรูปภาพ มากกว่าคำอธิบายจากผู้ใช้\n\n"
                
                "เกณฑ์ความสำคัญ (ตามที่เห็นในรูป):\n"
                "🔴 HIGH (ต้องแก้ไขภายในวันนี้):\n"
                "   • ไฟไหม้ ไฟฟ้าลัดวงจร ไฟช็อต ประกายไฟ\n"
                "   • ไฟดับทั้งหมด ไฟดับทั้งอาคาร ไฟดับพื้นที่กว้าง\n"
                "   • เสาไฟล้ม เสาไฟโค่น อุปกรณ์ไฟฟ้าหลักเสียหาย\n"
                "   • น้ำท่วมในห้อง ระบบประปาแตก น้ำรั่วรุนแรง\n"
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
                
                "หน้าที่:\n"
                "1. **วิเคราะห์รูปภาพเป็นหลัก** - ให้ความสำคัญกับสิ่งที่เห็นในรูป 80%\n"
                "2. วิเคราะห์ภาพรวมของรูปภาพ (สภาพแวดล้อม ความเสียหายรอบๆ)\n"
                "3. ใช้คำอธิบายจากผู้ใช้เป็นบริบทเสริมเท่านั้น ไม่ใช่ตัวหลัก (20%)\n"
                "4. **ตัวอย่าง**: ถ้ารูปแสดงหลอดไฟธรรมดา แต่ผู้ใช้เขียนว่า 'ไฟไหม้!!!' → ควรตอบ Low หรือ Medium ตามรูป\n\n"
                "Format ตอบ: 'Summary || Urgency || Detailed_Analysis'\n"
                "- Summary: สรุปปัญหาสั้นๆ (ไม่เกิน 80 ตัวอักษร)\n"
                "- Urgency: ประเมินความเร่งด่วน (High, Medium, Low) **ตามรูปภาพเป็นหลัก**\n"
                "- Detailed_Analysis: แสดงผลการวิเคราะห์แบบกระชับ แบ่งเป็น 2 หัวข้อหลัก:\n"
                "  • วิเคราะห์ตามรายละเอียดและรูปภาพ: [เนื้อหากระชับ]\n"
                "  • วิเคราะห์ภาพรวมของรูปภาพ: [เนื้อหากระชับ]"
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
        
        # 7. สร้างข้อความตอบกลับ
        success_msg = (
            f"✅ รับแจ้งร้องเรียนเรียบร้อยแล้วค่ะ!\n\n"
            f"📌 เรื่อง: {user_desc}\n"
            f"📷 ได้รับรูปภาพแล้ว\n"
            f"เจ้าหน้าที่จะรีบดำเนินการตรวจสอบให้นะคะ ขอบคุณค่ะ 🙏"
        )
        
        return success_msg
        
    except Exception as e:
        print(f"❌ Error in process_web_complaint_image: {e}")
        import traceback
        traceback.print_exc()
        return "เกิดข้อผิดพลาดในการประมวลผลค่ะ โปรดลองอีกครั้ง"

# ================= Debug API =================

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
                "image_url": item.get("image_url"), # เพิ่ม image_url สำหรับเว็บ
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


# ================= ยิง Cron เข้า =================
@app.route('/healthz', methods=['GET'])
def healthz_check():
    return "OK", 200

# ================= ROOT ENDPOINT =================

@app.route('/')
def home():
    return "Smart Condo Backend API is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(host='0.0.0.0', port=port, debug=debug_mode)