from google import genai
from google.genai import types
from ..config import Config
from .db import kb_col, chat_history_col
import re
import json
import datetime
from .lookup import normalize_name

# Initialize Client
client = genai.Client(api_key=Config.GEMINI_API_KEY)
MODEL_NAME = 'gemini-2.0-flash'
EMBEDDING_MODEL = 'text-embedding-004'

CHAT_SYSTEM_PROMPT = """
You are "Nong Bot Niti", a highly intelligent and polite Condo Assistant.

**CRITICAL**: When answering questions, PRIORITIZE information from PDF documents in the knowledge base.
- PDF sources contain official condo regulations, rules, and policies.

Rules for Interaction:
1. **PDF Priority**: If the answer exists in a PDF document, use it FIRST.
2. **Citation Style**: 
   - DO NOT mention the specific filename (e.g., "1_GC_Regulations.pdf"). 
   - Instead, use natural language references like "ตามระเบียบของคอนโด" (According to condo regulations) or "ตามข้อบังคับ" (According to by-laws).
   - ONLY mention the PAGE NUMBER if it's crucial for the user to look it up (e.g., "ระบุไว้ในหน้า 3").
3. **Database Strictness**: Use the [CONDO KNOWLEDGE BASE] for all facts.
   - If information is NOT in the database, say "ขออภัยค่ะ ข้อมูลส่วนนี้ไม่มีในระบบของนิติฯ ค่ะ" or similar.
   - DO NOT invent shops, menus, or services.
4. **No Hallucinations**: You are forbidden from using general knowledge to supplement missing database facts.
5. **Billing & Utilities**: You CAN perform basic arithmetic for billing/expenses.
6. **Intent & Typos**: Infer user intent even if there are typos.
7. **Conversation Flow**: Use [CHAT HISTORY] to maintain context.
8. **Tone**: Polite Thai ("ค่ะ/ครับ"). Use "ค่ะ" as default.
9. **User Addressing**: When referring to the user, ALWAYS use the format: " คุณ[Name] " (Note the spaces).
"""

def extract_keywords(text):
    """Enhanced keyword extraction with typo correction and intent expansion."""
    try:
        # Common Thai typo corrections
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
- "หิวข้าว"/"หาอาหาร"/"หอวข้าว" → อาหาร ร้านอาหาร เซเว่น ร้านค้า
- "จอดรถ"/"ที่จอด" → จอดรถ ที่จอดรถ ลานจอด
- "ฟิตเนส"/"สระน้ำ"/"ส่วนกลาง" → สิ่งอำนวยความสะดวก ฟิตเนส ออกกำลังกาย สระว่ายน้ำ

User Input: "{corrected_text}"

Return ONLY keywords (space-separated):"""
        
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        keywords = res.text.strip().split()
        print(f"🔑 Keywords: {keywords} (from: '{text}')")
        return keywords
    except Exception as e:
        print(f"AI Keyword Error: {e}")
        corrected = text
        for typo, correct in typo_map.items():
            corrected = corrected.replace(typo, correct)
        return corrected.split()

def generate_embedding(text):
    """
    Generate 768-dimensional vector embedding for text using Gemini.
    """
    try:
        # New SDK v1
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text
        )
        return result.embeddings[0].values
    except Exception as e:
        print(f"❌ Embedding Error: {e}")
        return []

def retrieve_knowledge(query, limit=15):
    """Enhanced hybrid search strategy with PDF prioritization and holistic search."""
    try:
        # 0. Special Handling: Identity Questions (Who/Where/What Project)
        identity_keywords = ['ที่นี่ที่ไหน', 'โครงการอะไร', 'ชื่อคอนโด', 'นิติบุคคลที่ไหน', 'ติดต่อใคร', 'เบอร์โทร', 'what condo', 'where is this']
        force_page_one = any(k in query.lower() for k in identity_keywords)
        
        # 1. Generate Query Vector
        vector = generate_embedding(query)
        
        results = []
        seen_ids = set()
        
        # 2. Vector Search (Atlas)
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
                            "topic": 1, 
                            "content": 1, 
                            "tags": 1, 
                            "source": 1,
                            "page": 1,
                            "type": 1,
                            "score": {"$meta": "vectorSearchScore"}
                        }
                    }
                ]
                vector_results = list(kb_col.aggregate(pipeline))
                print(f"✅ Vector search found: {len(vector_results)} results")
        except Exception as ve:
             print(f"⚠️ Vector Search unavailable: {ve}")
        
        # 3. Text Search (Broader scope)
        keywords = extract_keywords(query)
        if force_page_one:
            keywords.append("โครงการ") # Add 'Project' to ensure we hit titles
            
        keyword_str = " ".join(keywords)
        print(f"🔍 Hybrid Search Keywords: {keyword_str}")
        
        text_results = []
        try:
            # Search EVERYTHING in the KB with text match
            cursor = kb_col.find(
                {"$text": {"$search": keyword_str}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(20)
            text_results = list(cursor)
        except Exception as e:
             pass
             
        # 4. Force Page 1 Injection (if identity question)
        page_one_results = []
        if force_page_one:
            print("🚀 Identity Question Detected: Injecting PDF Covers...")
            # Fetch Page 1 from all PDFs
            page_one_results = list(kb_col.find({"type": "pdf", "page": 1}).limit(5))
            
        # Merge Strategy
        all_candidates = page_one_results + vector_results + text_results
        
        # Deduplication and Formatting
        for r in all_candidates:
            rid = str(r.get('_id', ''))
            if rid and rid not in seen_ids:
                r['_id'] = rid
                
                # Normalize source/page info
                if r.get('type') == 'pdf':
                    src = r.get('source', 'Unknown PDF')
                    pg = r.get('page', '?')
                    # Citation uses proper naming now
                    r['source_citation'] = f"PDF: {src} (Page {pg})"
                else:
                    r['source_citation'] = "ADMIN KNOWLEDGE BASE"
                    
                results.append(r)
                seen_ids.add(rid)
                
                if len(results) >= 15:
                    break
        
        return results
    except Exception as e:
        print(f"❌ RAG Error: {e}")
        return []

def analyze_parcel_label(image_data):
    """
    Analyze image data using Gemini's native JSON output mode for maximum speed and reliability.
    """
    try:
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

        # UPDATED PROMPT: Direct, Fast, Strict Mapping
        system_instruction = """
You are an expert Thai OCR engine specialized in deciphering **Handwritten (ลายมือ)** and Printed Shipping Labels.
Extract text visually and output strict JSON.

### CRITICAL RULES:
- **HANDWRITING:** Expect messy, cursive, or faint handwriting. Use context to infer characters.
- **SPEED:** Scan efficiently. If a value is illegible, return "N/A".

### EXTRACTION RULES:

1. **transport** (Logistics Company):
   - LOOK AT THE LOGO/HEADER FIRST.
   - **NORMALIZE STRICTLY:**
     - SPX / Shopee -> "SPX EXPRESS"
     - Flash -> "FLASH EXPRESS"
     - Kerry -> "KERRY EXPRESS"
     - J&T -> "J&T EXPRESS"
     - Post / Thailand Post -> "Thailand Post"
     - DHL -> "DHL"
     - Ninja -> "NINJA VAN"
   - If unknown, return "N/A".

2. **recipient_name**:
   - Locate "ผู้รับ" or "TO". The text immediately following is the name.
   - **Separation:** If a number appears at the end of the name line, split it! That is likely the Room Number.
   - Keep ONLY the name. Remove titles (นาย/นาง/คุณ).

3. **room_number**:
   - **PRIORITY 1 (The "Next-to-Name" Rule):** The room number is most often written **right after the recipient's name** on the same line.
     - Example: "สมชาย 123/45" -> Room is "123/45"
     - Example: "นิดา (888)" -> Room is "888"
   - **PRIORITY 2:** The line immediately BELOW the name.
   - **HANDWRITING:** Watch out for messy digits. "/" might look like "1" or "|". Convert Thai digits (๑ -> 1) if found.
   - **Anti-Hallucination:** Do not confuse "Price/COD" (typically on the far right, often with currency symbols) with Room Number. However, if a number is next to the name, it is likely the Room, even if it looks simple.
   - **FORMAT:** Prefer "XX/YY" or pure numbers. Ignore "Soi", "Moo", "Road".

4. **tracking_number**:
   - The code under the barcode (TH..., KER..., SPX...).
   - If not found, return "N/A".

5. **is_label**:
   - true if it looks like a shipping label.

### PROCESSING ORDER:
1. Logo -> `transport`
2. Barcode -> `tracking_number`
3. Receiver Line -> `recipient_name` & `room_number` (Focus on Handwriting interpretation)
"""
        
        response = client.models.generate_content(
            model=MODEL_NAME,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type='application/json',
                response_schema=response_schema,
                temperature=0.1, # Slightly relaxed for Handwriting inference
                # top_k removed to allow better handwriting probability search
            ),
            contents=[
                types.Part.from_bytes(data=image_data, mime_type='image/jpeg')
            ]
        )
        
        result = json.loads(response.text.strip())
        
        # Safety Sanitize: Remove Price/COD artifacts if AI failed
        room = result.get('room_number', '')
        if room and room != "N/A":
            # Remove obvious price indicators
            if any(x in room.upper() for x in ['THB', 'BAHT', '.00', 'COD']):
                 room = re.sub(r'(?i)(THB|Baht|COD|Price|\.00)', '', room).strip()
            
            # If it looks like a phone number (0xxxxxxxxx), clear it
            if re.match(r'^0\d{9}$', room.replace('-', '')):
                room = ""
            
            result['room_number'] = room
        elif room == "N/A":
            result['room_number'] = "" # Convert N/A to empty string for frontend consistency

        return result
        
    except Exception as e:
        print(f"AI Label Analysis Error: {e}")
        return None

def check_match(scanned_data, user_profile):
    """
    Robust comparison between scanned data and user profile.
    """
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
    """
    Extract both intent and embedded selection from user input.
    """
    try:
        prompt = f"""Analyze Thai text to extract BOTH the intent and any embedded selection (numbers/PINs).

[Intent Rules]
- 'register_outside': Register for after-hours (ลงทะเบียน, รับนอกเวลา, ขอรับนอกเวลา)
- 'cancel': Cancel registration (ยกเลิก, ย้ายกลับ, ยกเลิกนอกเวลา)
- 'pick_parcel': ONLY numbers/ranges (1, 1-3, ชิ้น2, รหัส1234)
- 'check_parcel': Check status (เช็ก, ดูพัสดุ, มีพัสดุไหม)
- 'general': Everything else

Text: "{text}"

If text contains BOTH intent AND selection (e.g., "ขอรับนอกเวลา45632", "ยกเลิกชิ้น1"), extract BOTH.
If ONLY intent (e.g., "ลงทะเบียน"), selection is null.
If ONLY selection (e.g., "45632", "ชิ้น1"), intent is 'pick_parcel'.

Return JSON format ONLY:
{{"intent": "register_outside|cancel|pick_parcel|check_parcel|general", "selection": "extracted_number_or_null"}}"""

        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        # Clean markdown
        result_text = res.text.strip().replace('```json', '').replace('```', '').strip()
        result = json.loads(result_text)
        
        intent = result.get('intent', 'general').lower()
        selection = result.get('selection')
        
        if selection in ['null', 'None', '', 'none']:
            selection = None
            
        valid_intents = ['register_outside', 'check_parcel', 'pick_parcel', 'cancel', 'general']
        if intent not in valid_intents:
            intent = 'general'
            
        print(f"🔍 Intent: {intent}, Selection: {selection}")
        return (intent, selection)
        
    except Exception as e:
        print(f"Intent Extraction Error: {e}")
        # Fallback
        text_lower = text.lower()
        numbers = re.findall(r'\d+', text)
        
        if 'ลงทะเบียน' in text or 'รับนอกเวลา' in text or 'ขอรับนอก' in text:
            return ('register_outside', numbers[0] if numbers else None)
        elif 'ยกเลิก' in text:
            return ('cancel', numbers[0] if numbers else None)
        elif 'เช็ก' in text or 'ดูพัสดุ' in text:
            return ('check_parcel', None)
        elif numbers:
            return ('pick_parcel', numbers[0])
        else:
            return ('general', None)

def analyze_intent(text):
    """Legacy compatibility wrapper."""
    intent, _ = extract_intent_and_selection(text)
    return intent

def generate_chat_response(user_text, user_context={}):
    """
    Generates a response using Gemini + RAG + Chat History.
    """
    try:
        # 1. Use Active Context
        history_context = ""
        raw_history = user_context.get('history', [])
        
        if raw_history:
            history_text = []
            for h in raw_history:
                role_label = "AI" if h.get('role') == 'assistant' else "User"
                msg = h.get('message', '')
                if msg:
                    history_text.append(f"{role_label}: {msg}")
            
            if history_text:
                history_context = "\n".join(history_text)
            else:
                history_context = "No previous history."
        else:
            history_context = "No previous history."
        
        # 2. RAG Step
        docs = retrieve_knowledge(user_text)
        if docs:
            kb_context = "\n".join([
                f"\n[Document: {d.get('source_citation','Unknown')}]\n"
                f"Topic: {d.get('topic','-')}\n"
                f"Content: {d.get('content','')}\n" 
                f"Tags: {', '.join(d.get('tags',[]))}" 
                for d in docs
            ])
        else:
            kb_context = "No specific condo internal data found for this query."
            
        user_info = f"User Name: {user_context.get('first_name','Guest')}\nUser Room: {user_context.get('room_number','-')}"
        
        full_prompt = f"""
        {CHAT_SYSTEM_PROMPT}
        
        [CONDO KNOWLEDGE BASE]
        {kb_context}
        
        [USER PROFILE]
        {user_info}
        
        [CHAT HISTORY]
        {history_context}
        
        [CURRENT USER MESSAGE]
        User: {user_text}
        
        Instruction: 
        - Refer to the USER as "คุณ[Name]" with spaces.
        - Answer ONLY based on the KNOWLEDGE BASE. 
        - If unsure, say you don't have the info yet.
        - Be helpful and professional.
        
        Answer (Thai):
        """
        
        response = client.models.generate_content(model=MODEL_NAME, contents=full_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gen Chat Error: {e}")
        return "ขออภัยค่ะ น้องบอตกำลังประมวลผลข้อมูล โปรดรอสักครู่หรือลองใหม่ภายหลังค่ะ"

def extract_selection_ids(text, parcels):
    """
    Comprehensive parcel selection extraction.
    """
    try:
        print(f"🔍 extract_selection_ids called with text: '{text}'")
        
        parcel_info = []
        parcel_by_index = {}
        parcel_by_pin = {}
        
        for i, p in enumerate(parcels, 1):
            pin = str(p.get('pin'))
            parcel_info.append(f"Index: {i}, PIN: {pin}, Tracking: {p.get('tracking_number')}, Courier: {p.get('transport')}")
            parcel_by_index[i] = pin
            parcel_by_pin[pin] = p
        
        text_clean = text.strip()
        selected_pins = []
        
        has_thai = bool(re.search(r'[\u0E00-\u0E7F]', text_clean))
        
        # Strategy 1: Pure number handling
        if not has_thai:
            print("📊 Using regex for pure number input")
            
            # Ranges
            range_match = re.match(r'^(\d+)\s*-\s*(\d+)$', text_clean)
            if range_match:
                start_idx = int(range_match.group(1))
                end_idx = int(range_match.group(2))
                for idx in range(start_idx, end_idx + 1):
                    if idx in parcel_by_index:
                        selected_pins.append(parcel_by_index[idx])
                return selected_pins
            
            # Comma-separated
            if ',' in text_clean:
                parts = re.split(r'[,\s]+', text_clean)
                for part in parts:
                    if part.isdigit():
                        idx = int(part)
                        if idx in parcel_by_index:
                            selected_pins.append(parcel_by_index[idx])
                return selected_pins if selected_pins else []
            
            # Space-separated
            if ' ' in text_clean:
                parts = text_clean.split()
                for part in parts:
                    if part.isdigit():
                        num = int(part)
                        if 1 <= num <= len(parcels):
                            if num in parcel_by_index:
                                selected_pins.append(parcel_by_index[num])
                if selected_pins:
                    return selected_pins
            
            # Pure digits (PIN vs Index)
            if text_clean.isdigit():
                digits = text_clean
                if len(digits) >= 5: # PIN
                    if digits in parcel_by_pin:
                        return [digits]
                    return []
                else: # Index sequential e.g. "12" -> 1,2
                    for digit_char in digits:
                        idx = int(digit_char)
                        if idx in parcel_by_index:
                            selected_pins.append(parcel_by_index[idx])
                    return selected_pins if selected_pins else []
        
        # Strategy 2: AI for complex input
        print("🤖 Using AI for complex input")
        info_str = "\n".join(parcel_info)
        
        prompt = f"""
        User wants to select parcels from this list:
        {info_str}
        
        User input: "{text}"
        
        TASK: Extract ALL selected parcels and return their PIN codes.
        OUTPUT FORMAT: Return ONLY a valid JSON array of PIN strings.
        Examples: ["1234"], ["1234", "5678"], []
        """
        
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        txt = res.text.strip().replace('```json', '').replace('```', '').strip()
        
        if not txt or txt.lower() in ["none", "null"]:
            return []
            
        selected_pins = json.loads(txt)
        if isinstance(selected_pins, list):
            result = [str(p) for p in selected_pins]
            return result
        else:
            return []
            
    except Exception as e:
        print(f"❌ Extraction Error: {e}")
        return []