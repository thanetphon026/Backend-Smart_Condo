"""
AI Service Module - Smart Condo Backend  
Handles all Google Gemini AI interactions for intelligent features
"""
import json
import datetime
from functools import lru_cache
from config import gemini_client
from google.genai import types
from database import kb_col, users_col, parcels_col, chat_history_col

# ================= AI MODEL CONFIGURATION =================
# Using Gemini 2.0 Flash for better multimodal and Thai language support
AI_MODEL = 'gemini-2.0-flash-exp'

# ================= SYSTEM PROMPTS =================

CHAT_SYSTEM_PROMPT = """
คุณคือ "น้องบอตนิติ" ผู้ช่วยอัจฉริยะประจำคอนโดลุมพ Continue.
บุคลิก: เป็นมนุษย์, สุภาพมาก, มีความเห็นอกเห็นใจ, กระตือรือร้นที่จะช่วยเหลือ และดูเป็นมืออาชีพแต่เข้าถึงง่าย

กฎการตอบ:
1. ตอบกระชับ ตรงประเด็น ไม่พูดยืดยาว
2. **ห้าม** แทรกเรื่องพัสดุเมื่อผู้ใช้ไม่ได้ถามถึง
3. **ห้าม** เปิดเผยข้อมูลของห้องอื่นหรือบุคคลอื่น
4. ถ้าไม่มีข้อมูล ตอบอย่างชัดเจนว่า "ขออภัยค่ะ ไม่มีข้อมูลในระบบ"
5. ใช้ภาษาไทยที่เป็นธรรมชาติ เว้นวรรคถูกต้อง
6. ถ้าผู้ใช้ถามเรื่องพัสดุ ให้ตอบตามข้อมูลที่ให้ไว้ใน Context
"""

# ================= INTENT RECOGNITION =================

@lru_cache(maxsize=256)
def analyze_intent(text):
    """
    Analyze user intent with AI
    Returns: str - Intent category (CHECK_STATUS, GENERAL, OTHER)
    """
    try:
        text_clean = text.strip().lower()
        
        # Quick rule-based check for common patterns
        general_keywords = ["กฎระเบียบ", "เบอร์โทร", "เบอร์ฉุกเฉิน", "วิธีใช้", "บริการ", "ค่าบริการ"]
        if any(keyword in text_clean for keyword in general_keywords):
            return "GENERAL"
        
        prompt = f"""วิเคราะห์ความตั้งใจของผู้ใช้: '{text}'

Output Format (JSON):
{{
  "intent": "CHECK_STATUS" | "GENERAL" | "OTHER"
}}

Rules:
1. CHECK_STATUS: ถามเกี่ยวกับสถานะพัสดุ (เช่น "มีพัสดุไหม", "เช็คพัสดุ")
2. GENERAL: ถามเรื่องกฎระเบียบ, ข้อมูลทั่วไป, บริการ
3. OTHER: ทักทาย, คุยเรื่องอื่น

ตอบเฉพาะชื่อ category."""
        
        response = gemini_client.models.generate_content(
            model=AI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        result = json.loads(response.text.strip())
        return result.get("intent", "OTHER")
        
    except Exception as e:
        print(f"⚠️ Intent Analysis Error: {e}")
        return "OTHER"

@lru_cache(maxsize=128)
def extract_keywords(user_text):
    """
    Extract keywords from user text for knowledge base search
    Returns: list of keywords
    """
    try:
        analysis_prompt = f"""สกัดคำหลัก (Keywords) ภาษาไทย 2-3 คำจากข้อความ: '{user_text}'

เน้นคำที่เป็น: อุปกรณ์, กฎระเบียบ, กิจกรรม
ตอบเฉพาะคำหลักคั่นด้วยช่องว่าง"""
        
        response = gemini_client.models.generate_content(
            model=AI_MODEL,
            contents=analysis_prompt
        )
        return response.text.strip().split()
    except:
        return []

# ================= PARCEL VERIFICATION (NEW) =================

def verify_parcel_image(image_url, pending_parcels_data):
    """
    Verify if uploaded image is a parcel and matches user's pending parcels
    
    Args:
        image_url: URL of the uploaded image
        pending_parcels_data: List of dict containing pending parcel info (room_number, recipient_name)
    
    Returns:
        dict: {
            "is_parcel": bool,
            "extracted_room": str or None,
            "extracted_name": str or None,
            "matches": bool,
            "matched_parcel": dict or None,
            "confidence": float
        }
    """
    try:
        # Prepare prompt with pending parcel info
        pending_info = "\n".join([
            f"- ห้อง {p['room_number']}, ชื่อ: {p.get('recipient_name', 'N/A')}"
            for p in pending_parcels_data
        ])
        
        prompt = f"""วิเคราะห์รูปภาพนี้:

1. รูปนี้เป็นพัสดุ (กล่อง/ซอง พร้อมฉลากที่อยู่) หรือไม่?
2. ถ้าเป็นพัสดุ สกัดข้อมูล:
   - เลขห้อง (Room Number)
   - ชื่อผู้รับ (Recipient Name)

3. เปรียบเทียบกับ ข้อมูลพัสดุที่ลงทะเบียนไว้:
{pending_info}

Output Format (JSON):
{{
  "is_parcel": true/false,
  "extracted_room": "เลขห้อง หรือ null",
  "extracted_name": "ชื่อผู้รับ หรือ null",
  "matches": true/false,
  "matched_parcel_room": "เลขห้องที่ตรง หรือ null",
  "confidence": 0.0-1.0
}}

Rules:
- is_parcel คือ ต้องเห็นกล่อง/ซอง + ฉลากชัดเจน
- matches คือ extracted_room และ extracted_name ตรงกับรายการที่ลงทะเบียน
- confidence คือ ความมั่นใจในการจับคู่ (0-1)
"""
        
        response = gemini_client.models.generate_content(
            model=AI_MODEL,
            contents=[
                {"text": prompt},
                {"file_uri": image_url}
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        result = json.loads(response.text.strip())
        
        # Find matched parcel details
        matched_parcel = None
        if result.get("matches") and result.get("matched_parcel_room"):
            matched_room = result["matched_parcel_room"]
            matched_parcel = next(
                (p for p in pending_parcels_data if matched_room in str(p['room_number'])),
                None
            )
        
        result["matched_parcel"] = matched_parcel
        
        print(f"🔍 Parcel Verification: {result}")
        return result
        
    except Exception as e:
        print(f"❌ Parcel Verification Error: {e}")
        return {
            "is_parcel": False,
            "extracted_room": None,
            "extracted_name": None,
            "matches": False,
            "matched_parcel": None,
            "confidence": 0.0
        }

# ================= PARCEL EXTRACTION FROM IMAGE =================

def extract_parcel_info_from_image(image_url):
    """
    Extract parcel information from scanned image
    
    Args:
        image_url: URL of parcel image
    
    Returns:
        dict: {
            "success": bool,
            "room_number": str,
            "recipient_name": str,
            "courier": str,
            "tracking_number": str,
            "error": str or None
        }
    """
    try:
        prompt = """วิเคราะห์รูปพัสดุนี้และสกัดข้อมูลต่อไปนี้:

1. เลขห้อง (Room Number)
2. ชื่อผู้รับ (Recipient Name) - ชื่อเต็ม
3. บริษัทขนส่ง (Courier) - เช่น Kerry, Flash, Thailand Post, J&T
4. เลขพัสดุ (Tracking Number)

Output Format (JSON):
{{
  "room_number": "เลขห้อง",
  "recipient_name": "ชื่อ นามสกุล",
  "courier": "ชื่อบริษัทขนส่ง",
  "tracking_number": "เลขติดตามพัสดุ"
}}

Rules:
- ถ้าอ่านไม่ออก ใส่ "-"
- เลขห้องต้องเป็นตัวเลข
- ชื่อผู้รับเป็นภาษาไทยหรือภาษาอังกฤษ
- บริษัทขนส่งให้ชื่อเต็ม ไม่ย่อ
"""
        
        response = gemini_client.models.generate_content(
            model=AI_MODEL,
            contents=[
                {"text": prompt},
                {"file_uri": image_url}
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        result = json.loads(response.text.strip())
        result["success"] = True
        result["error"] = None
        
        print(f"📦 Extracted Parcel Info: {result}")
        return result
        
    except Exception as e:
        print(f"❌ Parcel Extraction Error: {e}")
        return {
            "success": False,
            "room_number": "-",
            "recipient_name": "-",
            "courier": "-",
            "tracking_number": "-",
            "error": str(e)
        }

# ================= RAG (Retrieval-Augmented Generation) =================

def get_knowledge_context(user_text, user):
    """
    Get context from knowledge base and user data for RAG
    
    Args:
        user_text: User's question
        user: User document from database
    
    Returns:
        str: Formatted context string
    """
    context_parts = []
    
    try:
        # Personal Data
        user_info = f"ผู้ใช้งาน: {user.get('first_name', 'ลูกบ้าน')} {user.get('last_name', '')} (ห้อง {user.get('room_number', 'ไม่ระบุ')})"
        
        # Parcels
        parcel_context = f"รายการพัสดุ:\n🏠 ห้อง {user.get('room_number', '-')}\n📦 ตอนนี้ยังไม่มีพัสดุค้างอยู่นะคะ"
        
        if user.get('room_number'):
            room_clean = str(user['room_number']).replace("ห้อง", "").strip()
            my_parcels = list(parcels_col.find({
                "room_number": {"$regex": f".*{room_clean}.*"}, 
                "status": "pending"
            }))
            
            if my_parcels:
                count = len(my_parcels)
                p_str = f"รายการพัสดุ:\n🏠 ห้อง {user['room_number']}\n📦 มีพัสดุคงค้างทั้งหมด {count} ชิ้น\n"
                
                item_lines = []
                for idx, p in enumerate(my_parcels, 1):
                    line = f"{idx}. บริษัทขนส่ง: {p.get('transport')} | เลขพัสดุ: {p.get('tracking_number')} | PIN: {p.get('pin')}"
                    item_lines.append(line)
                
                p_str += "\n".join(item_lines)
                p_str += "\n\nถ้าจะรับพัสดุแจ้ง PIN ให้พนักงานได้เลยนะคะ"
                parcel_context = p_str
        
        personal_data_str = f"[ข้อมูลส่วนตัวของผู้ใช้]\n{user_info}\n{parcel_context}\n"
        context_parts.append(personal_data_str)

        # Knowledge Base - RAG search
        ai_keywords = extract_keywords(user_text)
        
        search_query = {}
        if ai_keywords:
            or_conditions = []
            for kw in ai_keywords:
                or_conditions.append({"topic": {"$regex": kw, "$options": "i"}})
                or_conditions.append({"content": {"$regex": kw, "$options": "i"}})
            search_query = {"$or": or_conditions}
        
        candidates = list(kb_col.find(search_query).limit(15))
        
        scored_results = []
        user_text_lower = user_text.lower()

        for doc in candidates:
            topic = str(doc.get('topic', '')).lower()
            content = str(doc.get('content', '')).lower()
            score = 0
            
            for kw in ai_keywords:
                kw_low = kw.lower()
                if kw_low in topic: score += 15
                if kw_low in content: score += 5
            
            if user_text_lower in topic or user_text_lower in content:
                score += 30
            
            if score > 0:
                scored_results.append((score, f"หัวข้อ: {doc.get('topic')}\nรายละเอียด: {doc.get('content')}"))

        scored_results.sort(key=lambda x: x[0], reverse=True)
        top_knowledge = [res[1] for res in scored_results[:3]]

        if top_knowledge:
            kb_str = "[คลังความรู้]\n" + "\n---\n".join(top_knowledge)
            context_parts.append(kb_str)
        else:
            context_parts.append("[คลังความรู้]\nไม่พบข้อมูลที่เกี่ยวข้องในคู่มือ")

        return "\n\n".join(context_parts)
    except Exception as e:
        print(f"❌ RAG Context Error: {e}")
        return None

# ================= CHATBOT RESPONSE GENERATION =================

def generate_chat_response(user_message, context, chat_history=[]):
    """
    Generate chatbot response using Gemini with context and history
    
    Args:
        user_message: User's message
        context: Context string from RAG
        chat_history: List of previous messages
    
    Returns:
        str: AI response
    """
    try:
        full_prompt = f"""{CHAT_SYSTEM_PROMPT}

[Context]
{context}

[User Message]
{user_message}

ตอบกระชับ เป็นธรรมชาติ และเป็นมิตร"""
        
        response = gemini_client.models.generate_content(
            model=AI_MODEL,
            contents=full_prompt
        )
        
        return response.text.strip()
        
    except Exception as e:
        print(f"❌ Chat Response Error: {e}")
        return "ขออภัยค่ะ ขณะนี้ระบบมีปัญหา กรุณาลองใหม่อีกครั้งค่ะ"

# ================= CHAT HISTORY MANAGEMENT =================

def save_chat_message(line_user_id, role, message, platform="line", image_url=None):
    """
    Save chat message to full chat history and user's recent history
    
    Args:
        line_user_id: LINE User ID
        role: 'user' or 'assistant'
        message: Message content
        platform: 'line' or 'web'
        image_url: Optional image URL
    """
    try:
        # Normalize role
        if role == 'assistant' or role == 'model':
            role = 'assistant'
        
        # Save to full chat history collection
        chat_entry = {
            "line_user_id": line_user_id,
            "role": role,
            "message": message,
            "platform": platform,
            "image_url": image_url,
            "timestamp": datetime.datetime.utcnow()
        }
        chat_history_col.insert_one(chat_entry)
        
        # Save to user's recent history (keep last 10)
        entry_for_user = {
            "role": role if role != 'assistant' else 'model',
            "parts": [message],
            "timestamp": datetime.datetime.utcnow()
        }
        if image_url:
            entry_for_user["image_url"] = image_url
        
        users_col.update_one(
            {"line_user_id": line_user_id},
            {"$push": {"chat_history": {"$each": [entry_for_user], "$slice": -10}}}
        )
        
        print(f"💾 Saved chat: {role} message for {line_user_id}")
        return True
    except Exception as e:
        print(f"❌ Save Chat Error: {e}")
        return False
