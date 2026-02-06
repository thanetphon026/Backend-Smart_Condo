from google import genai
from google.genai import types
from ..config import Config
from .db import kb_col, chat_history_col
import re
import json
import datetime
import io
from PIL import Image  # ต้องลง pip install Pillow
from .lookup import normalize_name

# Initialize Client
client = genai.Client(api_key=Config.GEMINI_API_KEY)
MODEL_NAME = 'gemini-2.0-flash'  # ใช้ Flash เพื่อความไวสูงสุด
EMBEDDING_MODEL = 'text-embedding-004'

CHAT_SYSTEM_PROMPT = """
You are "Nong Bot Niti", a highly intelligent and polite Condo Assistant.

**CRITICAL**: When answering questions, PRIORITIZE information from PDF documents in the knowledge base.
- PDF sources contain official condo regulations, rules, and policies.

Rules for Interaction:
1. **PDF Priority**: If the answer exists in a PDF document, use it FIRST.
2. **Citation Style**: 
   - DO NOT mention the specific filename. 
   - Instead, use natural language references like "ตามระเบียบของคอนโด" (According to condo regulations).
   - ONLY mention the PAGE NUMBER if it's crucial.
3. **Database Strictness**: Use the [CONDO KNOWLEDGE BASE] for all facts.
   - If information is NOT in the database, say "ขออภัยค่ะ ข้อมูลส่วนนี้ไม่มีในระบบของนิติฯ ค่ะ".
   - DO NOT invent shops, menus, or services.
4. **No Hallucinations**: You are forbidden from using general knowledge to supplement missing database facts.
5. **Billing & Utilities**: You CAN perform basic arithmetic.
6. **Intent & Typos**: Infer user intent even if there are typos.
7. **Conversation Flow**: Use [CHAT HISTORY] to maintain context.
8. **Tone**: Polite Thai ("ค่ะ/ครับ"). Use "ค่ะ" as default.
9. **User Addressing**: When referring to the user, ALWAYS use the format: " คุณ[Name] " (Note the spaces).
"""

def extract_keywords(text):
    """Enhanced keyword extraction with typo correction and intent expansion."""
    try:
        typo_map = {
            'หอวข้าว': 'หาอาหาร', 'หอว': 'หา', 'หวิข้าว': 'หิวข้าว',
            'เซเวน': 'เซเว่น', 'ร้านาหาร': 'ร้านอาหาร',
            'ส่วนกลาง': 'สิ่งอำนวยความสะดวก'
        }
        
        corrected_text = text
        for typo, correct in typo_map.items():
            corrected_text = corrected_text.replace(typo, correct)
        
        prompt = f"""Analyze the user input, correct any Thai typos, and extract 3-5 Thai keywords for condo knowledge base.

Infer intent even from misspellings:
- "หิวข้าว"/"หาอาหาร" → อาหาร ร้านอาหาร เซเว่น ร้านค้า
- "จอดรถ"/"ที่จอด" → จอดรถ ที่จอดรถ ลานจอด
- "ฟิตเนส"/"สระน้ำ" → สิ่งอำนวยความสะดวก ฟิตเนส สระว่ายน้ำ

User Input: "{corrected_text}"

Return ONLY keywords (space-separated):"""
        
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        keywords = res.text.strip().split()
        return keywords
    except Exception as e:
        print(f"AI Keyword Error: {e}")
        return text.split()

def generate_embedding(text):
    """Generate 768-dimensional vector embedding."""
    try:
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text
        )
        return result.embeddings[0].values
    except Exception as e:
        print(f"❌ Embedding Error: {e}")
        return []

def retrieve_knowledge(query, limit=15):
    """Enhanced hybrid search strategy."""
    try:
        identity_keywords = ['ที่นี่ที่ไหน', 'โครงการอะไร', 'ชื่อคอนโด', 'นิติบุคคลที่ไหน', 'ติดต่อใคร', 'เบอร์โทร', 'what condo']
        force_page_one = any(k in query.lower() for k in identity_keywords)
        
        vector = generate_embedding(query)
        results = []
        seen_ids = set()
        
        # Vector Search
        vector_results = []
        try:
            if vector:
                pipeline = [
                    {
                        "$vectorSearch": {
                            "index": "vector_index", 
                            "path": "embedding", 
                            "queryVector": vector,
                            "numCandidates": 100,
                            "limit": 20
                        }
                    },
                    {
                        "$project": {
                            "topic": 1, "content": 1, "tags": 1, "source": 1, "page": 1, "type": 1,
                            "score": {"$meta": "vectorSearchScore"}
                        }
                    }
                ]
                vector_results = list(kb_col.aggregate(pipeline))
        except Exception as ve:
             print(f"⚠️ Vector Search unavailable: {ve}")
        
        # Text Search
        keywords = extract_keywords(query)
        if force_page_one: keywords.append("โครงการ")
        keyword_str = " ".join(keywords)
        
        text_results = []
        try:
            cursor = kb_col.find(
                {"$text": {"$search": keyword_str}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(20)
            text_results = list(cursor)
        except Exception:
             pass
             
        # Page 1 Injection
        page_one_results = []
        if force_page_one:
            page_one_results = list(kb_col.find({"type": "pdf", "page": 1}).limit(5))
            
        all_candidates = page_one_results + vector_results + text_results
        
        for r in all_candidates:
            rid = str(r.get('_id', ''))
            if rid and rid not in seen_ids:
                r['_id'] = rid
                if r.get('type') == 'pdf':
                    src = r.get('source', 'Unknown PDF')
                    pg = r.get('page', '?')
                    r['source_citation'] = f"PDF: {src} (Page {pg})"
                else:
                    r['source_citation'] = "ADMIN KNOWLEDGE BASE"
                results.append(r)
                seen_ids.add(rid)
                if len(results) >= 15: break
        
        return results
    except Exception as e:
        print(f"❌ RAG Error: {e}")
        return []

# --- NEW OPTIMIZED OCR SECTION ---

def optimize_image(image_bytes, max_size=1024):
    """
    Preprocessing image for Speed & Accuracy:
    1. Grayscale (L): Helps with faded thermal labels.
    2. Resize: Limits max dimension to 1024px to reduce latency.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("L") # Convert to grayscale
        
        ratio = min(max_size / image.width, max_size / image.height)
        if ratio < 1:
            new_size = (int(image.width * ratio), int(image.height * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85)
        return output.getvalue()
    except Exception as e:
        print(f"⚠️ Image Optimization Failed: {e}")
        return image_bytes

def analyze_parcel_label(image_data):
    """
    Ultimate Thai Logistics OCR:
    - Supports all major carriers (Kerry, Flash, SPX, J&T, DHL, etc.)
    - Strict logic for Room Number (Ignores Soi/Road).
    - Auto-corrects transport based on tracking number patterns.
    """
    try:
        # 1. Optimize Image
        optimized_image = optimize_image(image_data)

        response_schema = {
            "type": "OBJECT",
            "properties": {
                "recipient_name": {"type": "STRING"},
                "room_number": {"type": "STRING"},
                "transport": {"type": "STRING"},
                "tracking_number": {"type": "STRING"},
                "is_label": {"type": "BOOLEAN"}
            },
            "required": ["recipient_name", "room_number", "transport", "tracking_number", "is_label"]
        }

        # 2. Comprehensive System Prompt
        system_instruction = """
You are an expert Logistics OCR engine specialized in Thai Shipping Labels.
Extract visual text and return strict JSON.

### 1. TRANSPORT COMPANY (Logistics Detection)
Identify the logo/header. Map strictly to these STANDARD NAMES:
- **Major Thai:** "Kerry Express", "Flash Express", "SPX Express", "J&T Express", "Thailand Post", "Ninja Van", "DHL", "Best Express", "SCG Express"
- **Global:** "FedEx", "UPS", "TNT"
- **Rule:** If "Shopee" or "SPX" logo -> "SPX Express".

### 2. RECIPIENT NAME (ผู้รับ)
- Find "To:", "ผู้รับ:", "C/O".
- **CLEANING:** Remove titles (คุณ, นาย, นาง). Remove phone numbers.
- **CRITICAL:** If name is mixed with address (e.g. "Somchai 88/1"), EXTRACT ONLY NAME.

### 3. ROOM NUMBER (เลขห้อง)
- **TARGET:** Look for "Room", "ห้อง", or pattern "XX/YY" or "XXX".
- **STRICT EXCLUSION:** DO NOT confuse "Soi" (ซอย), "Moo" (หมู่), "Road" (ถนน) with Room Number.
- If text is "Soi 5", Room is NOT 5.
- Format: Return ONLY digits or "XX/YY".

### 4. TRACKING NUMBER (เลขพัสดุ)
- The barcode text (Alphanumeric).
- Flash/SPX often starts with "TH".
- Kerry often starts with "KEA", "KER".

### 5. IS_LABEL
- true if it looks like a shipping label.
"""
        
        response = client.models.generate_content(
            model=MODEL_NAME, # Gemini 2.0 Flash
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type='application/json',
                response_schema=response_schema,
                temperature=0.0 # Strict & Deterministic
            ),
            contents=[
                types.Part.from_bytes(data=optimized_image, mime_type='image/jpeg')
            ]
        )
        
        result = json.loads(response.text.strip())
        
        # 3. Logic Validation & Correction
        if result.get('is_label'):
            track = result.get('tracking_number', '').upper().replace(" ", "")
            transport = result.get('transport', 'Unknown')
            
            # Auto-correct Transport based on Tracking Pattern
            if track.startswith("TH") and len(track) > 10 and transport == "Unknown":
                result['transport'] = "Flash Express" # Most likely in TH
            elif track.startswith("KEA") or track.startswith("KER"):
                result['transport'] = "Kerry Express"
            elif track.startswith("SPX"):
                result['transport'] = "SPX Express"
                
            result['tracking_number'] = track
            
        return result
        
    except Exception as e:
        print(f"❌ Smart Label Analysis Error: {e}")
        return None

# --- END OPTIMIZED OCR SECTION ---

def check_match(scanned_data, user_profile):
    """Robust comparison between scanned data and user profile."""
    if not scanned_data or not scanned_data.get('is_label'):
        return {
            "is_match": False, 
            "reason": "ไม่พบข้อมูลพัสดุจากรูปภาพ", 
            "matched_fields": [], 
            "ocr_details": scanned_data or {}
        }
    
    # Normalizers
    def normalize_room(room_str):
        if not room_str or room_str == "N/A": return ""
        return str(room_str).strip().replace(" ", "").replace("ห้อง", "").replace("Room", "").replace("room", "").replace("/", "")

    scanned_room = normalize_room(scanned_data.get('room_number'))
    user_room = normalize_room(user_profile.get('room_number'))
    
    scanned_name = normalize_name(scanned_data.get('recipient_name'))
    first_name = normalize_name(user_profile.get('first_name', ''))
    last_name = normalize_name(user_profile.get('last_name', ''))
    display_name = normalize_name(user_profile.get('display_name', ''))
    full_name = (first_name or '') + (last_name or '')

    matched_fields = []
    
    # 1. Room Match
    room_match = False
    if scanned_room and user_room:
        if scanned_room == user_room or scanned_room in user_room or user_room in scanned_room:
            room_match = True
            matched_fields.append("เลขห้อง")

    # 2. Name Match
    name_match = False
    if scanned_name:
        if (first_name and (scanned_name in first_name or first_name in scanned_name)) or \
           (last_name and (scanned_name in last_name or last_name in scanned_name)) or \
           (display_name and (scanned_name in display_name or display_name in scanned_name)) or \
           (full_name and (scanned_name in full_name or full_name in scanned_name)):
            name_match = True
            matched_fields.append("ชื่อ-นามสกุล")

    is_match = room_match and name_match
    
    if is_match:
        reason = "ข้อมูลถูกต้อง ตรงกับฐานข้อมูล"
    elif room_match:
        reason = "พบเลขห้องที่ถูกต้อง แต่ชื่อผู้รับไม่ชัดเจน"
    elif name_match:
        reason = "พบชื่อที่ถูกต้อง แต่เลขห้องไม่ตรง"
    else:
        reason = "ข้อมูลไม่ตรงกับบัญชีผู้ใช้งานนี้"

    return {
        "is_match": is_match,
        "reason": reason,
        "matched_fields": matched_fields,
        "ocr_details": scanned_data
    }

def extract_intent_and_selection(text):
    """Extract both intent and embedded selection from user input."""
    try:
        prompt = f"""Analyze Thai text to extract BOTH the intent and any embedded selection (numbers/PINs).

[Intent Rules]
- 'register_outside': Register for after-hours (ลงทะเบียน, รับนอกเวลา, ขอรับนอกเวลา)
- 'cancel': Cancel registration (ยกเลิก, ย้ายกลับ, ยกเลิกนอกเวลา)
- 'pick_parcel': ONLY numbers/ranges (1, 1-3, ชิ้น2, รหัส1234)
- 'check_parcel': Check status (เช็ก, ดูพัสดุ, มีพัสดุไหม)
- 'general': Everything else

Text: "{text}"

Return JSON format ONLY:
{{"intent": "register_outside|cancel|pick_parcel|check_parcel|general", "selection": "extracted_number_or_null"}}"""

        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        result_text = res.text.strip().replace('```json', '').replace('```', '').strip()
        result = json.loads(result_text)
        
        intent = result.get('intent', 'general').lower()
        selection = result.get('selection')
        if selection in ['null', 'None', '', 'none']: selection = None
            
        return (intent, selection)
    except Exception as e:
        print(f"Intent Extraction Error: {e}")
        # Fallback Logic
        text_lower = text.lower()
        numbers = re.findall(r'\d+', text)
        if 'ลงทะเบียน' in text or 'รับนอกเวลา' in text:
            return ('register_outside', numbers[0] if numbers else None)
        elif 'ยกเลิก' in text:
            return ('cancel', numbers[0] if numbers else None)
        elif numbers:
            return ('pick_parcel', numbers[0])
        else:
            return ('general', None)

def analyze_intent(text):
    intent, _ = extract_intent_and_selection(text)
    return intent

def generate_chat_response(user_text, user_context={}):
    """Generates a response using Gemini + RAG + Chat History."""
    try:
        # History Context
        history_context = "No previous history."
        raw_history = user_context.get('history', [])
        if raw_history:
            history_text = [f"{'AI' if h.get('role')=='assistant' else 'User'}: {h.get('message','')}" for h in raw_history]
            history_context = "\n".join(history_text)
        
        # RAG Context
        docs = retrieve_knowledge(user_text)
        if docs:
            kb_context = "\n".join([f"- {d.get('content','')} (Source: {d.get('source_citation')})" for d in docs])
        else:
            kb_context = "No specific condo internal data found."
            
        user_info = f"User: {user_context.get('first_name','Guest')}, Room: {user_context.get('room_number','-')}"
        
        full_prompt = f"""
        {CHAT_SYSTEM_PROMPT}
        
        [KNOWLEDGE BASE]
        {kb_context}
        
        [USER INFO]
        {user_info}
        
        [HISTORY]
        {history_context}
        
        User: {user_text}
        
        Answer (Thai):
        """
        response = client.models.generate_content(model=MODEL_NAME, contents=full_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gen Chat Error: {e}")
        return "ขออภัยค่ะ ระบบขัดข้องชั่วคราว โปรดลองใหม่ภายหลังค่ะ"

def extract_selection_ids(text, parcels):
    """Comprehensive parcel selection extraction."""
    try:
        parcel_info = [f"Index: {i+1}, PIN: {p.get('pin')}" for i, p in enumerate(parcels)]
        parcel_by_index = {i+1: str(p.get('pin')) for i, p in enumerate(parcels)}
        
        # Simple Numeric Check
        if text.isdigit() and len(text) < 5:
            idx = int(text)
            if idx in parcel_by_index: return [parcel_by_index[idx]]
            
        # AI Extraction for complex queries
        prompt = f"""User wants to select parcels from: {parcel_info}
        User input: "{text}"
        Return JSON array of PINs. Example: ["1234", "5678"] or []"""
        
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        txt = res.text.strip().replace('```json', '').replace('```', '').strip()
        selected = json.loads(txt)
        return [str(p) for p in selected] if isinstance(selected, list) else []
    except Exception:
        return []