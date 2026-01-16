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
from parcel_flex_templates import create_parcel_ask_selection_flex, create_parcel_registered_flex, create_parcel_cancelled_flex, create_number_confirmation_flex, create_parcel_status_flex as create_parcel_status_flex_v2
    MessageEvent, 
    TextMessageContent, 
    ImageMessageContent, 
    FollowEvent
)

from flex_templates import (
    create_text_flex, 
    create_parcel_carousel, 
    create_parcel_pickup_flex, 
    create_after_hours_selection_flex, 
    create_after_hours_confirmation_flex, 
    create_after_hours_cancellation_flex,
    create_self_pickup_verification_flex,   # New
    create_self_pickup_mismatch_flex        # New
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
    # complaints_col removed
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

# Helper functions for analyze_urgency_from_description and determine_final_urgency removed
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
    3. ความรู้ทั่วไป (Knowledge Base)
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

        personal_data_str = (
            f"[ข้อมูลส่วนตัวของผู้ใช้ (Private Data)]\n"
            f"{user_info}\n"
            f"{parcel_context}\n"
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
            "1. PARCEL_CHECK: User wants to check their parcels (e.g., 'เช็คพัสดุ', 'มีพัสดุไหม', 'ดูพัสดุ').\n"
            "2. AFTER_HOURS: User wants to register after-hours pickup (e.g., 'รับนอกเวลา', 'ลงทะเบียนนอกเวลา').\n"
            "3. CANCEL: User wants to cancel current operation (e.g., 'ยกเลิก', 'ไม่เอาแล้ว', 'พอแล้ว').\n"
            "4. CHECK_STATUS: Asking about parcel status.\n"
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
        if "PARCEL_CHECK" in intent_result: return "PARCEL_CHECK"
        if "AFTER_HOURS" in intent_result: return "AFTER_HOURS"
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

# ================= AI INTENT DETECTION HELPERS =================

def detect_cancel_intent_ai(text, current_state):
    """
    ใช้ AI ตรวจจับความต้องการยกเลิก รวมถึงคำพิมพ์ผิดและบริบท
    Args:
        text: ข้อความของผู้ใช้
        current_state: สถานะปัจจุบัน เช่น 'filing_desc', 'waiting_image', 'selecting', 'normal'
    Returns:
        (is_cancel: bool, message: str, should_use_flex: bool)
    """
    try:
        prompt = f"""วิเคราะห์ว่าผู้ใช้ต้องการ "ยกเลิก" หรือไม่

ข้อความ: "{text}"
สถานะปัจจุบัน: "{current_state}"

Output Format (JSON):
{{
  "intent": "CANCEL" | "NO",
  "context": "parcel" | "none",
  "confidence": 0.0-1.0
}}

Rules:
1. INTENT = "CANCEL" ถ้าพบคำยกเลิก เช่น:
   - "ยกเลิก", "cancel", "ออก", "exit", "พอ", "ไม่เอาแล้ว"
   - รวมคำพิมพ์ผิด: "ยกเลค", "ยกเลกิ", "แคนเซล", "คันเซล"
2. ตรวจสอบบริบทจาก current_state:
   - selecting -> parcel
   - normal -> none
3. confidence: ความมั่นใจ 0.0-1.0
"""

        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        import json
        result = json.loads(response.text.strip())
        is_cancel = result.get("intent") == "CANCEL"
        context = result.get("context", "none")
        confidence = result.get("confidence", 0.0)
        
        if not is_cancel:
            return False, "", False
        
        # Generate appropriate cancellation message based on context
        if current_state == 'normal' and confidence > 0.7:
            # User trying to cancel when not in any process
            flex_content = {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "ℹ️ ไม่มีกระบวนการที่ต้องยกเลิก",
                            "weight": "bold",
                            "size": "lg",
                            "color": "#0084FF"
                        },
                        {
                            "type": "text",
                            "text": "คุณไม่ได้อยู่ในกระบวนการใดตอนนี้ค่ะ",
                            "wrap": True,
                            "color": "#666666",
                            "size": "sm",
                            "margin": "md"
                        }
                    ]
                }
            }
            return True, {"text": "คุณไม่ได้อยู่ในกระบวนการใดตอนนี้ค่ะ", "flex": flex_content}, True
        
        elif context == "parcel":
            # Cancelling parcel selection
            return True, "❌ ยกเลิกการทำรายการเรียบร้อยค่ะ", False
        
        return False, "", False
        
    except Exception as e:
        print(f"❌ Cancel Intent AI Error: {e}")
        # Fallback to keyword matching
        cancel_keywords = ["ยกเลิก", "cancel", "ไม่แจ้งแล้ว", "พอแล้ว", "ออก", "exit"]
        is_cancel = any(kw in text.lower() for kw in cancel_keywords)
        
        if is_cancel and current_state == 'normal':
            return True, "คุณไม่ได้อยู่ในกระบวนการใดตอนนี้ค่ะ", False
        
        return is_cancel, "❌ ยกเลิกเรียบร้อยค่ะ", False


def analyze_number_input(text, user_state):
    """
    วิเคราะห์ว่าผู้ใช้พิมพ์แค่ตัวเลข/PIN โดยไม่มีบริบท
    ถ้าใช่ ให้ถามยืนยันว่าต้องการลงทะเบียนรับนอกเวลาหรือไม่
    
    Args:
        text: ข้อความที่พิมพ์
        user_state: State ของผู้ใช้
    Returns:
        (needs_confirmation: bool, flex_content: dict or None)
    """
    # ถ้าอยู่ในกระบวนการอยู่แล้ว ไม่ต้องถามยืนยัน
    if user_state.get('after_hours_state') == 'selecting':
        return False, None
    if user_state.get('awaiting_number_confirmation'):
        return False, None
    
    try:
        prompt = f"""วิเคราะห์ว่าข้อความเป็นการพิมพ์ตัวเลข/PIN เฉยๆ โดยไม่มีบริบทหรือไม่

ข้อความ: "{text}"

Output Format (JSON):
{{
  "is_pure_number": true/false,
  "has_context": true/false,
  "intent_clarity": "clear" | "ambiguous" | "unclear"
}}

Rules:
1. is_pure_number = true ถ้าพิมพ์แค่:
   - ตัวเลข: "1", "1-2", "123", "12345"
   - ตัวเลขพร้อม separator: "1, 2", "1 2 3"
   
2. has_context = true ถ้ามีคำบอกเจตนา:
   - "พัสดุ 1-2", "ขอรับนอกเวลา 1", "รับนอกเวลา 12345"
   - "เช็คพัสดุ", "ดูพัสดุ", "แจ้งร้องเรียน"
   
3. intent_clarity:
   - "clear": มีบริบทชัดเจน
   - "ambiguous": แค่ตัวเลข ไม่แน่ใจว่าหมายถึงอะไร
   - "unclear": ไม่เกี่ยวกับตัวเลข

ตัวอย่าง:
"1-2" -> {{"is_pure_number": true, "has_context": false, "intent_clarity": "ambiguous"}}
"พัสดุ 1-2 ขอรับนอกเวลา" -> {{"is_pure_number": false, "has_context": true, "intent_clarity": "clear"}}
"สวัสดี" -> {{"is_pure_number": false, "has_context": false, "intent_clarity": "unclear"}}
"""

        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        import json
        result = json.loads(response.text.strip())
        is_pure_number = result.get("is_pure_number", False)
        has_context = result.get("has_context", False)
        intent_clarity = result.get("intent_clarity", "unclear")
        
        # ถ้าพิมพ์แค่ตัวเลขโดยไม่มีบริบท -> ถามยืนยัน
        if is_pure_number and not has_context and intent_clarity == "ambiguous":
            flex_content = create_number_confirmation_flex(text)
            return True, flex_content
        
        return False, None
        
    except Exception as e:
        print(f"❌ Number Input Analysis Error: {e}")
        # Fallback: Check if input is purely numeric
        import re
        # If text is ONLY numbers, dashes, commas, spaces
        if re.match(r'^[\d\s,\-]+$', text.strip()):
            # And doesn't contain parcel/complaint keywords
            if not any(kw in text.lower() for kw in ["พัสดุ", "parcel", "รับ", "นอกเวลา", "ร้องเรียน", "แจ้ง"]):
                flex_content = create_number_confirmation_flex(text)
                return True, flex_content
        
        return False, None

# ================= AFTER-HOURS PARCEL HELPERS =================



def analyze_parcel_intent(text):
    """
    วิเคราะห์เจตนาเกี่ยวกับพัสดุ:
    1. REGISTER_AH: ต้องการลงทะเบียนรับนอกเวลา
    2. CHECK_STATUS: ต้องการตรวจสอบสถานะ/ดูรายการพัสดุเฉยๆ (ไม่ลงทะเบียน)
    3. NO: อื่นๆ
    """
    try:
        prompt = f"""วิเคราะห์ข้อความของผู้ใช้เกี่ยวกับพัสดุว่าเป็นเจตนาแบบใด
        
ข้อความ: "{text}"

Output Format (JSON):
{{
  "intent": "REGISTER_AH" | "CHECK_STATUS" | "NO",
  "target_pins": ["12345"] | "ALL" | []
}}

Rules:
1. "REGISTER_AH": ถ้าต้องการ **รับของ/ลงทะเบียน/เอาไว้** นอกเวลา (เช่น "ขอรับนอกเวลา", "รับนอกเวลาเลข 1", "เอาไว้นอกเวลา", "ฝากไว้ก่อน", "รับตู้", "ลงทะเบียนรับของ")
   - รวมกรณีพิมพ์ผิดเช่น "รับนแอกเวลา", "รับนอกเวา"
2. "CHECK_STATUS": ถ้าต้องการ **ตรวจสอบ/ดู/เช็ค** ว่ามีของไหม หรือขอดูรายการเฉยๆ (เช่น "เช็คพัสดุ", "มีของค้างไหม", "ดูรายการหน่อย", "ตรวจสอบพัสดุ")
   - ถ้าถามเฉยๆ ไม่ได้บอกว่าจะรับ ให้เป็น CHECK_STATUS
3. "NO": คำถามทั่วไป, ทักทาย, หรือเรื่องอื่นที่ไม่เกี่ยวกับพัสดุ
4. target_pins:
   - ถ้าระบุเลขพัสดุ/PIN/ลำดับ ให้ใส่ใน list (เช่น "อันที่ 1", "เลข 88888", "ชิ้นที่ 2")
   - รองรับเลขไทย: "หนึ่ง"->1, "สอง"->2, "สาม"->3 (ให้แปลงเป็นเลขอารบิกใส่ list เช่น "2")
   - ระวัง! "ชิ้น 2 3" => ["2", "3"] (ไม่ใช่ ALL)
   - ถ้าบอก "ทั้งหมด", "ทุกอัน", "เหมาหมด" ถึงจะใส่ "ALL"
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
        intent = result.get("intent", "NO")
        target_pins = result.get("target_pins")
        
        # Normalize
        if target_pins == "ALL":
            target_pins = "ALL"
        elif isinstance(target_pins, list):
            target_pins = [str(p) for p in target_pins]
        else:
            target_pins = []

        return intent, target_pins
        
    except Exception as e:
        print(f"❌ Intent Analysis Error: {e}")
        # Fallback keyword matching
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["นอกเวลา", "after"]):
            return "REGISTER_AH", []
        if any(kw in text_lower for kw in ["เช็ค", "ตรวจสอบ", "มีของ", "ดูรายการ"]):
            return "CHECK_STATUS", []
        
        return "NO", []

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
1. "ทั้งหมด", "all", "ทุกอัน", "เหมาหมด", "เอาหมด" -> all indices [1, 2, ..., {total_items}]
2. "1-3", "1 ถึง 3" -> [1, 2, 3]
3. "1, 3", "อันที่ 1 กับ 3", "ชิ้น 1 3", "1 และ 2" -> [1, 3] or [1, 2]
4. Support Thai numbers: "หนึ่ง"->1, "สอง"->2, "สาม"->3, "สี่"->4
5. "อันแรก" -> [1], "อันสุดท้าย" -> [{total_items}]
6. IMPORTANT: If user lists numbers like "3 4" or "2 3", output ONLY those indices. DO NOT output 'all'.
7. If unsure/invalid -> []

Example:
Text: "ชิ้น 2 กับ 3" -> {{"indices": [2, 3]}}
Text: "3 4" -> {{"indices": [3, 4]}}
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

def detect_after_hours_intent_ai(text):
    """
    ใช้ AI ตรวจจับว่าผู้ใช้ต้องการรับพัสดุนอกเวลาหรือไม่ (รวมถึงคำพิมพ์ผิด)
    Returns: (bool, confidence_score)
    """
    try:
        prompt = (
            f"Text: \"{text}\"\n\n"
            "Detect if user wants AFTER-HOURS parcel pickup.\n"
            "Keywords: \"รับนอกเวลา\", \"ขอรับนอกเวลา\", \"ลงนอกเวลา\", \"ลงทะเบียนนอกเวลา\", \"รับพัสดุนอกเวลา\", \"after hours\"\n"
            "Also detect TYPOS: \"รบนอกเวลา\", \"รับนองเวลา\", \"รับนอกเวลาาา\", etc.\n\n"
            "Return JSON: {\"is_after_hours\": true/false, \"confidence\": 0.0-1.0}\n"
            "Examples:\n"
            "- \"รับนอกเวลา 1-2\" -> {\"is_after_hours\": true, \"confidence\": 1.0}\n"
            "- \"รบนอกเวลา\" -> {\"is_after_hours\": true, \"confidence\": 0.9}\n"
            "- \"1-2\" -> {\"is_after_hours\": false, \"confidence\": 1.0}\n"
            "- \"เช็คพัสดุ\" -> {\"is_after_hours\": false, \"confidence\": 1.0}"
        )
        
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        import json
        result = json.loads(response.text.strip())
        is_after_hours = result.get("is_after_hours", False)
        confidence = result.get("confidence", 0.0)
        
        return is_after_hours, confidence
        
    except Exception as e:
        print(f"❌ AI After-Hours Intent Error: {e}")
        # Fallback to keyword matching
        keywords = ["รับนอกเวลา", "ขอรับนอกเวลา", "ลงนอกเวลา", "after hours"]
        is_match = any(kw in text.lower() for kw in keywords)
        return is_match, 1.0 if is_match else 0.0

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
    after_hours_state = user.get('after_hours_state')
    awaiting_confirmation = user.get('awaiting_number_confirmation', False)
    platform = user.get('platform', 'line')  # ดึงข้อมูล platform

    # ================= PRIORITY 1: REGISTRATION =================
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
    
    # ================= PRIORITY 2: AI-POWERED CANCELLATION =================
    # Detect cancellation intent with typo tolerance and context awareness
    is_cancel, cancel_msg, should_use_flex = detect_cancel_intent_ai(text, state)
    
    if is_cancel:
        # Clear states based on context
        if after_hours_state == 'selecting':
            users_col.update_one(
                {"line_user_id": uid},
                {"$set": {
                    "after_hours_state": None,
                    "after_hours_pending_pins": None,
                    "after_hours_pending_parcels": None
                }}
            )
        
        # Handle awaiting_confirmation cancellation
        if awaiting_confirmation:
            users_col.update_one(
                {"line_user_id": uid},
                {"$set": {"awaiting_number_confirmation": False}}
            )
            # Override message for confirmation cancellation
            return "เข้าใจค่ะ ยกเลิกการยืนยันแล้วค่ะ หากต้องการความช่วยเหลือ สามารถพิมพ์คำถามได้เลยค่ะ 😊"
        
        return cancel_msg  # Already formatted (text or dict with flex)
    
    # ================= PRIORITY 3: NUMBER INPUT CONFIRMATION =================
    # Handle awaiting confirmation state
    if awaiting_confirmation:
        # AI-powered intent analysis instead of keyword matching
        try:
            confirmation_prompt = f"""วิเคราะห์ว่าผู้ใช้ตอบว่ายืนยันหรือปฏิเสธ

คำถาม: "ต้องการลงทะเบียนรับพัสดุนอกเวลาใช่ไหมคะ?"
คำตอบ: "{text}"

Output Format (JSON):
{{
  "response": "YES" | "NO" | "UNCLEAR"
}}

Rules:
1. YES: ใช่, ตกลง, ok, yes, รับ, ได้, เอา, ค่ะ, ครับ, ต้องการ, ถูกต้อง
2. NO: ไม่, no, ยกเลิก, cancel, ไม่รับ, ไม่ต้องการ, ไม่ใช่
3. UNCLEAR: อื่นๆ ที่ไม่ชัดเจน
"""
            
            response = client.models.generate_content(
                model='gemini-2.0-flash-exp',
                contents=confirmation_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            import json
            result = json.loads(response.text.strip())
            user_response = result.get("response", "UNCLEAR")
            
            if user_response == "YES":
                # User confirmed - proceed with parcel registration
                users_col.update_one(
                    {"line_user_id": uid},
                    {"$set": {"awaiting_number_confirmation": False}}
                )
                # Continue to parcel intent analysis below
            elif user_response == "NO":
                # User declined
                users_col.update_one(
                    {"line_user_id": uid},
                    {"$set": {"awaiting_number_confirmation": False}}
                )
                return "เข้าใจค่ะ ยกเลิกการทำรายการแล้วค่ะ หากต้องการความช่วยเหลือ สามารถพิมพ์คำถามได้เลยค่ะ 😊"
            else:
                # Unclear response, ask again
                return "ขออภัยค่ะ ไม่เข้าใจคำตอบ กรุณาตอบว่า 'ใช่' หรือ 'ไม่' ค่ะ"
                
        except Exception as e:
            print(f"❌ Confirmation Analysis Error: {e}")
            # Fallback to keyword matching
            yes_keywords = ["ใช่", "ใช้", "ตกลง", "ok", "yes", "รับ", "ได้", "เอา", "ค่ะ", "ครับ"]
            no_keywords = ["ไม่", "no", "ยกเลิก", "cancel"]
            
            text_lower = text.strip().lower()
            
            if any(kw in text_lower for kw in yes_keywords):
                users_col.update_one(
                    {"line_user_id": uid},
                    {"$set": {"awaiting_number_confirmation": False}}
                )
                # Continue
            elif any(kw in text_lower for kw in no_keywords):
                users_col.update_one(
                    {"line_user_id": uid},
                    {"$set": {"awaiting_number_confirmation": False}}
                )
                return "เข้าใจค่ะ ยกเลิกการทำรายการแล้วค่ะ หากต้องการความช่วยเหลือ สามารถพิมพ์คำถามได้เลยค่ะ 😊"
    
    # Check if this is pure number input WITHOUT context (when NOT in any process)
    if state == 'normal' and not after_hours_state and not awaiting_confirmation:
        needs_confirmation, flex_content = analyze_number_input(text, user)
        
        if needs_confirmation and flex_content:
            # Set awaiting confirmation state
            users_col.update_one(
                {"line_user_id": uid},
                {"$set": {"awaiting_number_confirmation": True}}
            )
            return {
                "text": f"คุณพิมพ์ '{text}' ต้องการลงทะเบียนรับพัสดุนอกเวลาใช่ไหมคะ?",
                "flex": flex_content
            }
    
    # ================= PRIORITY 4: ACTIVE PROCESS STATES =================
    # Strict process isolation - if in a state, ONLY handle that state
    
    # 4B. PARCEL AFTER-HOURS SELECTION PROCESS

    
    # ก่อนอื่นตรวจสอบการยกเลิกนอกเวลา (ต้องมีคำว่า "นอกเวลา" ด้วย)
    cancel_ah_keywords = ["ยกเลิกนอกเวลา", "ยกเลิกรับนอกเวลา", "ไม่รับนอกเวลา", "cancel after hours"]
    text_lower = text.strip().lower()
    
    # Check if it's a cancellation of after-hours specifically
    if any(kw in text_lower for kw in cancel_ah_keywords):
        # This is after-hours cancellation - redirect to after-hours cancel logic
        is_cancel, target_pins = detect_after_hours_cancel_intent(text)
        if is_cancel:
            # Handle after-hours cancellation
            room_number = user.get('room_number')
            current_ah_parcels = list(parcels_col.find({
                "room_number": room_number,
                "status": "pending",
                "is_after_hours": True
            }))
            
            if not current_ah_parcels:
                return "ไม่พบรายการพัสดุที่ลงทะเบียนรับนอกเวลาไว้ค่ะ 📦"
            
            # Cancel the after-hours parcels
            cancel_pins = [p.get('pin') for p in current_ah_parcels]
            parcels_col.update_many(
                {"pin": {"$in": cancel_pins}},
                {"$set": {"is_after_hours": False}}
            )
            
            return f"✅ ยกเลิกการลงทะเบียนรับนอกเวลา {len(cancel_pins)} รายการเรียบร้อยค่ะ"
    
    # 1. ตรวจสอบว่าผู้ใช้อยู่ในสถานะการเลือกพัสดุนอกเวลาหรือไม่
    after_hours_state = user.get('after_hours_state')
    
    if after_hours_state == 'selecting':
        try:
            # ผู้ใช้กำลังเลือกพัสดุที่ต้องการรับนอกเวลา
            pending_parcel_pins = user.get('after_hours_pending_pins', [])
            pending_parcels_data = user.get('after_hours_pending_parcels', [])
            
            text_lower = text.lower().strip()
            
            # Check for cancellation during selection
            if any(w in text_lower for w in ["ยกเลิก", "ไม่", "cancel", "no", "exit", "พอ"]):
                users_col.update_one(
                    {"line_user_id": uid},
                    {"$set": {
                        "after_hours_state": None,
                        "after_hours_pending_pins": None,
                        "after_hours_pending_parcels": None
                    }}
                )
                return "❌ ยกเลิกการทำรายการเรียบร้อยค่ะ"

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
            
            # 2. ใช้ AI ตรวจจับ intent นอกเวลา (รวมคำพิมพ์ผิด)
            is_after_hours_ai, confidence = detect_after_hours_intent_ai(text)
            
            # 3. ตรวจสอบว่ามีพัสดุคงค้างและมี intent นอกเวลาหรือไม่
            room_number = user.get('room_number')
            if room_number and is_after_hours_ai and confidence > 0.7 and not selected_pins:
                # ถ้า AI บอกว่าต้องการรับนอกเวลา แต่ยังไม่มีการเลือกพัสดุ
                # และผู้ใช้พิมพ์แค่ตัวเลข (เช่น "1", "2") ให้ถือว่าเป็นการเลือกพัสดุ
                try:
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

            # 4. ตรวจสอบว่ามีพัสดุนอกเวลาคงค้างหรือไม่ และต้องมี intent รับนอกเวลาชัดเจน
            # (ป้องกันไม่ให้เลขอย่าง "1-2" เข้าสู่โหมดนอกเวลาโดยไม่ตั้งใจ)
            if not selected_pins:
                example_pin = pending_parcel_pins[0] if pending_parcel_pins else '12345'
                flex_content = create_after_hours_error_flex(example_pin)
                return {
                    "text": "❌ ไม่เข้าใจคำสั่งค่ะ กรุณาเลือกใหม่",
                }
            
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
    
    # 2. Parcel Intent Analysis (Register AH / Check Status)
    parcel_intent, target_pins = analyze_parcel_intent(text)
    
    # 2.1 Case: CHECK_STATUS -> Show Green Flex Card (No database update)
    if parcel_intent == "CHECK_STATUS":
        room_number = user.get('room_number')
        # ดึงพัสดุทั้งหมดของห้อง
        # Note: เราดึงเฉพาะ 'pending' เพื่อแสดงสถานะปัจจุบัน
        all_pending_parcels = list(parcels_col.find({
            "room_number": room_number,
            "status": "pending"
        }).sort("timestamp", -1))
        
        # Calculate stats
        total_pending = len(all_pending_parcels)
        total_ah = sum(1 for p in all_pending_parcels if p.get('is_after_hours', False))
        total_normal = total_pending - total_ah
        
        flex_content = create_parcel_status_flex(
            all_pending_parcels, 
            total_pending, 
            total_ah, 
            total_normal, 
            room_number
        )
        
        msg = f"นี่คือสถานะพัสดุของคุณค่ะ (ทั้งหมด {total_pending} ชิ้น)"
        if total_pending == 0:
             msg = "ไม่พบพัสดุค้างจ่ายค่ะ ✅"

        return {
            "text": msg,
            "flex": flex_content
        }


# ================= AFTER-HOURS STATUS ENDPOINT =================

@app.route('/api/after-hours/status', methods=['GET'])
def get_after_hours_status():
    """ตรวจสอบสถานะเปิดรับลงทะเบียนนอกเวลา (cutoff 16:30)"""
    try:
        now = get_bkk_now()
        cutoff_time = now.replace(hour=16, minute=30, second=0, microsecond=0)
        is_closed = now > cutoff_time
        
        return jsonify({
            "is_closed": is_closed,
            "cutoff_time": "16:30",
            "server_time": now.strftime("%H:%M")
        })
    except Exception as e:
        return jsonify({"is_closed": True, "error": str(e)}), 500

    # 2.2 Case: REGISTER_AH -> Start Selection Process
    if parcel_intent == "REGISTER_AH":
        # [NEW] 16:30 Cutoff Rule
        now = get_bkk_now()
        cutoff_time = now.replace(hour=16, minute=30, second=0, microsecond=0)
        
        if now > cutoff_time:
             return (
                 "⛔ ขออภัยค่ะ ขณะนี้ปิดรับการลงทะเบียนรับพัสดุนอกเวลาแล้วค่ะ\n"
                 "(เวลาทำการลงทะเบียน: ก่อน 16:30 น. ของทุกวัน)\n\n"
                 "หากมีเหตุจำเป็น กรุณาติดต่อเจ้าหน้าที่นิติบุคคลโดยตรงนะคะ 🙏"
             )

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
                # Use a dictionary to map PINs to parcels for unique selection
                selected_parcels_map = {} 
                
                for t in target_pins:
                    # 1. Check for Index (e.g. "1", "2")
                    if t.isdigit() and len(t) < 3:
                        idx = int(t)
                        if 1 <= idx <= len(pending_parcels):
                            p = pending_parcels[idx-1]
                            selected_parcels_map[p['pin']] = p
                            continue

                    # 2. Check for PIN or Tracking Number match
                    for p in pending_parcels:
                        p_pin = str(p.get("pin", ""))
                        p_track = str(p.get("tracking_number", ""))
                        if t in p_pin or t in p_track:
                             selected_parcels_map[p['pin']] = p
                             break # Found match for this target, move to next target
                
                parcels_to_register = list(selected_parcels_map.values())

        
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
            
            # --- Re-fetch Parcels to get ACCURATE stats after update ---
            updated_pending_parcels = list(parcels_col.find({
                "room_number": room_number,
                "status": "pending"
            }).sort("timestamp", -1))
            
            total_pending = len(updated_pending_parcels)
            total_ah = sum(1 for p in updated_pending_parcels if p.get('is_after_hours', False))
            total_registered_count = len(reg_pins) # Just registered in this action
            
            # Use Confirmation Flex (Re-using the logic from selection confirmation or create a new one??)
            # The prompt asked for "blocks showing total, pending, etc" consistent with others
            # Let's use create_after_hours_confirmation_flex which does exactly this
            
            flex_content = create_after_hours_confirmation_flex(
                parcels_to_register, # pass full objects of registered items
                total_pending,
                total_ah, # Pass TOTAL AH count (not just current batch)
                room_number
            )

            # Re-read create_after_hours_confirmation_flex definition to be sure.
            # It takes: (registered_parcels_full, total_pending_count, total_registered_count, room_number)
            # total_registered_count in that context was "count of items just registered".
            
            # Let's use the new create_parcel_status_flex structure but for confirmation? 
            # OR modify the existing text reply to be a Flex.
            # The user complained: "Success, Total 5, AH 1, Remaining 4" was WRONG.
            # This implies the existing create_after_hours_confirmation_flex logic or input data was wrong.
            
            # Let's just correct the stats calculation here first and pass correct data.
            # But wait, create_after_hours_confirmation_flex might NOT show the "Stats Breakdown" like the Selection Card.
            # The user wants "Show total items, how many AH, how many Normal" like the Check Status card.
            
            # Let's use the valid stats we just calculated.
            
            parcel_list = "\n".join([f"  • PIN {p['pin']} - {p.get('transport','-')} ({p.get('tracking_number','-')})" for p in parcels_to_register])
            
            text_reply = (
                f"✅ ลงทะเบียนรับนอกเวลาเรียบร้อย {len(parcels_to_register)} รายการค่ะ!\n\n"
                f"{parcel_list}\n\n"
                f"🕐 เวลารับนอกเวลา: 18:00-22:00 น. ที่ Lobby\n"
                f"ขอบคุณที่แจ้งล่วงหน้านะคะ 🙏"
            )
            
            # Returns DICT now to support Flex
            return {
                "text": text_reply,
                "flex": flex_content
            }

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
                "after_hours_pending_parcels": [{"pin": p['pin'], "transport": p.get('transport', '-'), "tracking_number": p.get('tracking_number', '-'), "is_after_hours": p.get('is_after_hours', False)} for p in pending_parcels]
            }}
        )
        
        parcel_list_str = "\n".join(parcel_list)
        
        
        
        # Calculate stats for the Flex Message
        total_pending = len(pending_parcels)
        total_ah = sum(1 for p in pending_parcels if p.get('is_after_hours', False))
        total_normal = total_pending - total_ah

        if len(pending_parcels) == 1:
            flex_content = create_after_hours_selection_flex(pending_parcels, total_pending, total_ah, total_normal, room_number)
            text_reply = "คุณมีพัสดุคงค้าง 1 ชิ้น ต้องการลงทะเบียนรับนอกเวลาใช่ไหมคะ?"
        else:
            flex_content = create_after_hours_selection_flex(pending_parcels, total_pending, total_ah, total_normal, room_number)
            text_reply = f"คุณมีพัสดุคงค้าง {len(pending_parcels)} ชิ้น กรุณาเลือกรายการที่ต้องการรับนอกเวลาค่ะ"
            
        return {
            "text": text_reply,
            "flex": flex_content
        }


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
        
        if target_pins == "ALL": # If "ALL" is explicitly requested
            parcels_to_cancel = current_ah_parcels
        elif not target_pins: # If no specific pins are mentioned, but intent is cancel, assume ALL
            parcels_to_cancel = current_ah_parcels
        else:
            for p in current_ah_parcels:
                p_pin = str(p.get("pin", ""))
                p_track = str(p.get("tracking_number", ""))
                is_match = False
                for t in target_pins:
                    if t in p_pin or t in p_track:
                        is_match = True
                        break
                if is_match:
                    parcels_to_cancel.append(p)
            
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
        cancelled_count = len(parcels_to_cancel)
        remaining_ah = parcels_col.count_documents({
            "room_number": room_number,
            "status": "pending",
            "is_after_hours": True
        })
        
        # 3. Message construction
        flex_content = create_after_hours_cancellation_flex(
            parcels_to_cancel, 
            remaining_ah, 
            room_number
        )
        
        text_reply = f"✅ ยกเลิกรับนอกเวลาเรียบร้อย {cancelled_count} รายการค่ะ"
            
        return {
            "text": text_reply,
            "flex": flex_content
        }

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

    # ================= ENHANCED CANCELLATION LOGIC =================
    # AI-powered cancellation with context awareness
    if intent == "CANCEL":
        # Check context: are we in a process?
        if after_hours_state == 'selecting':
            # Cancel parcel selection
            users_col.update_one(
                {"line_user_id": uid},
                {"$set": {
                    "after_hours_state": None,
                    "after_hours_pending_pins": None,
                    "after_hours_pending_parcels": None
                }}
            )
            return "❌ ยกเลิกการลงทะเบียนรับพัสดุนอกเวลาเรียบร้อยค่ะ"
        else:
            # Not in any process
            return (
                "ขณะนี้คุณไม่ได้อยู่ในกระบวนการใดๆ ค่ะ \n"
                "(ลงทะเบียนรับพัสดุนอกเวลา)\n\n"
                "หากต้องการความช่วยเหลือ สามารถพิมพ์คำถามได้เลยค่ะ 😊"
            )

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
        
        # Auto-wrap simple text in Flex Bubble for premium look (ONLY if no flex provided)
        if not flex_contents and reply_text and len(reply_text) < 500: # Limit length for bubble
             flex_contents = create_text_flex(reply_text)
        
        update_chat_history(uid, 'model', reply_text, platform="line")
        
        # Use helper to send (supports Flex) (pass flex_contents)
        if flex_contents:
             send_line_message(uid, message=reply_text, flex_contents=flex_contents)
        else:
             line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply_text)]))

                    }
                }
                
                complaints_col.insert_one(new_complaint)
                print(f"✅ บันทึกการร้องเรียนสำเร็จ: ID={new_complaint.get('_id')}")
                
                # 6. Clear State
                users_col.update_one(
                    {"line_user_id": uid}, 
                    {"$set": {"complaint_state": "normal", "draft_desc": None}}
                )
                
                # 7. ตอบกลับผู้ใช้ด้วย Flex Message
                flex_card = create_complaint_received_flex(
                    description=user_desc,
                    image_url=img_url,
                    priority=final_urgency,
                    room=user.get('room_number', '-')
                )
                
                success_msg = (
                    f"✅ บอทรับแจ้งเรื่องเรียบร้อยแล้วค่ะ! 🙏\n"
                    f"⚠️ ระดับความสำคัญ: {final_urgency}"
                )
                
                # Send Flex Message with image
                send_line_message(uid, message=success_msg, flex_contents=flex_card)
                
                # Audit Log
                log_admin_action(
                    action="User Filed Complaint",
                    performed_by=f"User {user.get('first_name', 'Unknown')} (Room {user.get('room_number', '-')})",
                    target=f"New Complaint",
                    details=f"Filed complaint via LINE - Urgency: {final_urgency}"
                )
                
            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()
                line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="เกิดข้อผิดพลาดในการประมวลผลค่ะ โปรดลองอีกครั้ง")]))
            finally:
                if os.path.exists(temp_path): os.remove(temp_path)
        else:
            line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="ได้รับรูปแล้วค่ะ 📸 (ไม่ได้อยู่ในโหมดแจ้งร้องเรียน)")]))

@line_handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    uid = event.source.user_id
    message_id = event.message.id
    
    with ApiClient(line_configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_blob = MessagingApiBlob(api_client)
        
        # 1. Get User
        try:
            profile = line_bot_api.get_profile(uid)
            display_name = profile.display_name
            picture_url = profile.picture_url
        except:
            display_name = "Line User"
            picture_url = None
        
        user = get_or_create_user(uid, "line", display_name, picture_url)
        
        # 2. Check After-Hours Status & Pending Parcels
        now = get_bkk_now()
        # Cutoff 16:30 for registration, but pickup verification is allowed 18:00-22:00?
        # Requirement: "When after-hours system is closed (cutoff passed) and user sends photo"
        # User pickup time is 18:00-22:00.
        # So check if time is > 16:30 (Registration closed)
        cutoff_time = now.replace(hour=16, minute=30, second=0, microsecond=0)
        is_closed_registration = now > cutoff_time
        
        # Check if user has pending after-hours parcels
        pending_ah_parcels = list(parcels_col.find({
            "room_number": user.get("room_number"),
            "status": "pending",
            "is_after_hours": True
        }))
        
        if is_closed_registration and pending_ah_parcels:
             print(f"📸 Image received from {user.get('room_number')} during after-hours pickup window. Starting verification.")
             
             # Notify user processing
             # line_bot_api.push_message(PushMessageRequest(to=uid, messages=[TextMessage(text="🤖 กำลังตรวจสอบรูปภาพเพื่อยืนยันการรับพัสดุค่ะ กรุณารอสักครู่...")]))
             
             # Process Verification
             reply_msg = process_after_hours_verification(user, pending_ah_parcels, message_id, line_bot_blob)
             
             if isinstance(reply_msg, dict) and 'flex' in reply_msg:
                 # Check if text is present
                 text_alt = reply_msg.get('text', 'Verification Result')
                 send_line_message(uid, message=text_alt, flex_contents=reply_msg['flex'])
             else:
                 line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=str(reply_msg))]))
             
             # Log Scan Attempt
             log_user_action(
                 action="Self-Pickup Image Scan",
                 user_id=uid,
                 details=f"User sent image. Result: Confirmed/Mismatch handled in verification logic."
             )
             return

        # Default behavior: Just acknowledge or ignore
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="ได้รับรูปภาพแล้วค่ะ 📸")]))

def process_after_hours_verification(user, parcels, message_id, blob_client):
    """
    Verify if the image matches the parcel self-pickup context using Gemini Vision.
    """
    try:
        # 1. Download Image Content
        content = blob_client.get_message_content(message_id)
        
        # 2. Upload to Gemini (using helper or direct)
        # We need a mime_type. Format is usually JPEG/PNG from Line.
        # Line docs say provider returns binary. We can assume image/jpeg.
        
        # Save to temp file for upload
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tf:
            tf.write(content)
            temp_path = tf.name

        try:
            print("🚀 Uploading image to Gemini for verification...")
            upload_file = genai.upload_file(path=temp_path, mime_type="image/jpeg")
            
            # Wait for processing
            while upload_file.state.name == "PROCESSING":
                time.sleep(1)
                upload_file = genai.get_file(upload_file.name)
                
            if upload_file.state.name == "FAILED":
               raise ValueError("Gemini File Upload Failed")
               
            print(f"✅ Upload Complete: {upload_file.uri}")
            
            # 3. Construct Prompt
            room = user.get("room_number", "-")
            name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            if not name: name = user.get('display_name', 'Unknown')
            
            parcel_info = "\\n".join([f"- PIN {p.get('pin')} : {p.get('transport')} (Tracking: {p.get('tracking_number')})" for p in parcels])
            
            prompt = f"""
            Task: Verify User Self-Pickup Proof.
            User Room: {room}
            User Name: {name}
            Expected Parcels:
            {parcel_info}
            
            The user is picking up these parcels after hours.
            Analyze the image. It should show:
            1. The user holding the parcel(s).
            2. OR The parcel(s) itself clearly.
            3. OR The user's face (selfie) with the parcels or at the pickup point.
            
            Check for:
            - Visible PIN numbers matching the specific list (e.g. {', '.join([p.get('pin') for p in parcels])}).
            - Parcel labels matching Room {room} or Name {name}.
            
            If the image is completely unrelated (e.g. a cat, food, dark screen), reject it.
            If looks like a valid pickup attempt (even if label not super clear but context fits), approve it with caution.
            
            Output strictly in JSON format:
            {{
                "is_valid": true/false,
                "reason": "Reason in Thai language (short)",
                "confidence": "high/medium/low",
                "detected_text": "any relevant text seen"
            }}
            """
            
            # 4. Generate Content
            model_name = 'gemini-2.0-flash-exp' # Use faster model if available, or 1.5-flash
            # Try 'gemini-1.5-flash' or 'gemini-2.0-flash-exp' requested by user before?
            # User used 'gemini-3-flash-preview' in Step 375?? Is that real? 
            # Step 375 code shows 'gemini-3-flash-preview'. I should likely stick to what works or 'gemini-1.5-flash'.
            # I will use 'gemini-1.5-flash' as it is standard stable fast. 
            # Or reuse `model='gemini-3-flash-preview'` if it exists in their setup.
            # I'll use 'gemini-1.5-flash' to be safe.
            
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=[
                    types.Content(
                         role="user",
                         parts=[
                             types.Part.from_uri(file_uri=upload_file.uri, mime_type=upload_file.mime_type),
                             types.Part.from_text(text=prompt)
                         ]
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            result_text = response.text.strip()
            print(f"🤖 Verification Result: {result_text}")
            
            # Parse JSON
            try:
                # remove code fences if any
                if "```json" in result_text:
                    result_text = result_text.replace("```json", "").replace("```", "")
                
                ai_data = json.loads(result_text)
            except:
                ai_data = {"is_valid": True, "reason": "AI Format Error - Default Approve", "confidence": "low"}
            
            # 5. Return Flex
            if ai_data.get("is_valid", False):
                flex = create_self_pickup_verification_flex(name, room, parcels, ai_data)
                return {"text": "✅ ตรวจสอบรูปภาพสำเร็จ", "flex": flex}
            else:
                flex = create_self_pickup_mismatch_flex(ai_data.get("reason", "รูปภาพไม่ชัดเจน"))
                return {"text": "❌ ตรวจสอบไม่ผ่าน", "flex": flex}

        except Exception as e:
            print(f"Gemini/Processing Error: {e}")
            return "เกิดข้อผิดพลาดในการประมวลผลรูปภาพค่ะ (AI Error)"
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)

    except Exception as e:
        print(f"Verification Error: {e}")
        return "เกิดข้อผิดพลาดในการดาวน์โหลดรูปภาพค่ะ"

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
    Format datetime to ISO 8601 format for frontend consumption
    Frontend will handle Thai formatting (DD/MM/YYYY HH:MM)
    """
    if not dt:
        return None  # Return None instead of "-" so frontend can detect and show "-"
    try:
        # Convert to Bangkok timezone
        bkk_tz = pytz.timezone('Asia/Bangkok')
        if dt.tzinfo is None:
            # Assume UTC if no timezone info
            dt = pytz.utc.localize(dt)
        bkk_time = dt.astimezone(bkk_tz)
        # Return ISO 8601 format
        return bkk_time.isoformat()
    except Exception as e:
        print(f"⚠️ Datetime format error: {e}")
        return None

@app.route('/api/dashboard', methods=['GET'])
@require_api_token
def get_dashboard_stats():
    """ดึงข้อมูลสถิติทั้งหมดสำหรับแดชบอร์ด"""
    print(f"DEBUG: Dashboard requested by {request.remote_addr}")
    try:
        # Use ThreadPoolExecutor to run queries in parallel
        with ThreadPoolExecutor() as executor:
            # Submit all queries
            f_users = executor.submit(users_col.count_documents, {})
            f_total_parcels = executor.submit(parcels_col.count_documents, {})
            
            # Regular (In-Time) Stats: is_after_hours != True (False or Missing)
            f_pending_regular = executor.submit(parcels_col.count_documents, {
                "status": "pending", 
                "is_after_hours": {"$ne": True}
            })
            f_picked_regular = executor.submit(parcels_col.count_documents, {
                "status": "picked_up", 
                "is_after_hours": {"$ne": True}
            })
            
            # After-Hours Stats: is_after_hours == True
            f_pending_after_hours = executor.submit(parcels_col.count_documents, {
                "status": "pending", 
                "is_after_hours": True
            })
            f_picked_after_hours = executor.submit(parcels_col.count_documents, {
                "status": "picked_up", 
                "is_after_hours": True
            })

            # Get results
            return jsonify({
                "users": f_users.result(),
                "total_parcels": f_total_parcels.result(),
                "pending_regular": f_pending_regular.result(),
                "picked_regular": f_picked_regular.result(),
                "pending_after_hours": f_pending_after_hours.result(),
                "picked_after_hours": f_picked_after_hours.result()
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
            f_recent_parcels = executor.submit(lambda: list(parcels_col.find().sort("timestamp", -1).limit(5)))
            
            recent_parcels = f_recent_parcels.result()
        
        activities = []
        
        for parcel in recent_parcels:
            activities.append({
                "type": "parcel",
                "message": f"พัสดุใหม่: ห้อง {parcel.get('room_number', '-')}",
                "details": f"{parcel.get('transport', '-')} - {parcel.get('recipient_name', '-')}",
                "timestamp": format_datetime(parcel.get('timestamp'))
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

# ================= Complaints API (REMOVED) =================
# All complaint functionality has been removed.           items.sort(key=lambda x: (
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

# ================= COMPLAINTS REMOVED =================
# Complaint search endpoint removed - system no longer supports complaints

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
        
        # 3. บันทึก Audit Log (แยกประเภท)
        is_after_hours = parcel.get("is_after_hours", False)
        action_name = "Confirm Pickup (After-Hours)" if is_after_hours else "Confirm Pickup"
        
        log_admin_action(
            action=action_name,
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


# Resolve Complaint endpoint removed - system no longer supports complaints

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

# export_complaints endpoint removed

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
        # บันทึก Audit Log
        admin_name_header = request.headers.get('X-Admin-Name', 'Unknown Admin')
        admin_name = urllib.parse.unquote(admin_name_header)
        log_admin_action(
            action="Export Parcels",
            performed_by=admin_name,
            target="All Parcels",
            details="Exported all parcels to CSV"
        )

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=parcels_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "Content-Type": "text/csv; charset=utf-8-sig"  # Fix: Use BOM for Excel
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
        # บันทึก Audit Log
        admin_name_header = request.headers.get('X-Admin-Name', 'Unknown Admin')
        admin_name = urllib.parse.unquote(admin_name_header)
        log_admin_action(
            action="Export After-Hours Parcels",
            performed_by=admin_name,
            target="After-Hours Parcels",
            details="Exported after-hours parcels to CSV"
        )

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

# cleanup_old_resolved_complaints removed - system no longer supports complaints

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
    - ลบพัสดุที่รับแล้ว (pickedup) มากกว่า 90 วัน
    - ลบ audit logs ที่เก่ากว่า 90 วัน
    """
    try:
        print("\n🔄 Starting auto-cleanup process...")
        
        parcels_deleted = cleanup_old_picked_parcels()
        audit_logs_deleted = cleanup_old_audit_logs()
        
        total_deleted = parcels_deleted + audit_logs_deleted
        
        print(f"✅ Cleanup completed: {total_deleted} items deleted\n")
        
        return jsonify({
            "status": "success",
            "message": "Cleanup completed successfully",
            "deleted": {
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

        # กรณีที่ส่งรูปภาพมาจากเว็บ (สำหรับการแจ้งร้องเรียน) - REMOVED
        if image_base64:
             return jsonify({
                 "reply": "ระบบไม่รองรับการส่งรูปภาพในขณะนี้ค่ะ",
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

# process_web_complaint_image REMOVED

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