from google import genai
from google.genai import types
from ..config import Config
from .db import kb_col, chat_history_col
import re
import datetime

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

def retrieve_knowledge(query, limit=5):
    """Enhanced hybrid search strategy with PDF prioritization."""
    try:
        # 1. Generate Query Vector
        vector = generate_embedding(query)
        
        results = []
        seen_ids = set()
        
        # 2. Vector Search (Atlas)
        # Assuming index 'vector_index' is set up for 'embedding' field
        vector_results = []
        try:
            if vector:
                pipeline = [
                    {
                        "$vectorSearch": {
                            "index": "vector_index", 
                            "path": "embedding", 
                            "queryVector": vector,
                            "numCandidates": 50, 
                            "limit": 10  # Increased to get more candidates
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
             # This is expected if Atlas Vector Search is not enabled on this specific cluster tier
             print(f"⚠️ Vector Search unavailable (normal for free tier/no index): {ve}")
        
        # 3. Fallback/Augment with Text Search (Classic RAG)
        keywords = extract_keywords(query)
        keyword_str = " ".join(keywords)
        print(f"🔍 Hybrid Search Keywords: {keyword_str}")
        
        text_results = []
        try:
            # 3.1 Prioritize PDF content first (Official regs)
            cursor = kb_col.find(
                {
                    "$and": [
                        {"$text": {"$search": keyword_str}},
                        {"type": "pdf"}
                    ]
                },
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(limit)
            pdf_text_results = list(cursor)
            
            # 3.2 If PDFs found, great. If not, search everything.
            if len(pdf_text_results) < 3:
                cursor_all = kb_col.find(
                    {"$text": {"$search": keyword_str}},
                    {"score": {"$meta": "textScore"}}
                ).sort([("score", {"$meta": "textScore"})]).limit(limit)
                text_results = list(cursor_all)
            else:
                text_results = pdf_text_results
                
        except Exception as e:
            # Fallback for manual regex if text index missing
             pass
             
        # Merge Strategy: Prioritize PDFs, but mix in best vector matches
        all_candidates = vector_results + text_results
        
        # Separation
        pdfs = [r for r in all_candidates if r.get('type') == 'pdf']
        others = [r for r in all_candidates if r.get('type') != 'pdf']
        
        # Combine: PDFs first, then others
        final_list = pdfs + others
        
        for r in final_list:
            rid = str(r['_id'])
            if rid not in seen_ids:
                r['_id'] = rid
                # Normalize source/page info for AI context
                if r.get('type') == 'pdf':
                    src = r.get('source', 'Unknown PDF')
                    pg = r.get('page', '?')
                    r['source_citation'] = f"PDF: {src} (Page {pg})"
                else:
                    r['source_citation'] = "ADMIN KNOWLEDGE BASE"
                    
                results.append(r)
                seen_ids.add(rid)
        
        # 4. Fuzzy Fallback (only if total results are very low)
        if len(results) < 1: 
            import re
            regex_queries = []
            for kw in keywords:
                if len(kw) < 2: continue
                escaped_kw = re.escape(kw)
                regex_queries.extend([
                    {"topic": {"$regex": escaped_kw, "$options": "i"}},
                    {"content": {"$regex": escaped_kw, "$options": "i"}}
                ])
            if regex_queries:
                fuzzy = list(kb_col.find({"$or": regex_queries}).limit(3))
                for f in fuzzy:
                    rid = str(f['_id'])
                    if rid not in seen_ids:
                        f['_id'] = rid
                        f['source_citation'] = "FUZZY MATCH"
                        results.append(f)
                        seen_ids.add(rid)

        # Truncate
        return results[:8]
    except Exception as e:
        print(f"❌ RAG Error: {e}")
        return []

def analyze_parcel_label(image_data):
    """
    Analyze image data (bytes) using an expert OCR prompt to find Recipient Name, Room Number, 
    Tracking Number, and Logistics Company.
    """
    try:
        prompt = """
        Act as an expert OCR and Data Extraction AI specialized in Thai Logistics Labels. 
        Your task is to extract specific information from the provided shipping label images with 100% accuracy.

        Please analyze the image and extract the following 4 fields. If a field is not clearly visible or covered, mark it as "N/A".

        Fields to extract:
        1. Recipient Name (ชื่อผู้รับ):
           - Look for the text after "ผู้รับ (TO)" or "TO".
           - IMPORTANT: If a room number or house number (e.g., 28/548) is appended to the name, STRIP IT OUT and place it in the unit_number field.
           - Extract the full name strictly in Thai (or English if Thai is absent).
           - Ignore titles like "คุณ".

        2. House/Room Number (เลขห้อง/เลขที่บ้าน):
           - EXTRACT THE FULL IDENTIFIER: If the number is "28/456", extract "28/456".
           - PRIORITY LOCATIONS (Check in this order):
             1. IMMEDIATELY after Recipient Name.
             2. Top Right Corner / Header Box.
             3. "Remark" or "Note" field (often at bottom left or under barcode). Look closely here for moved room numbers.
             4. The END of the address lines.
             5. The START of the address (House Number/Building Number) -> Use this ONLY as a last resort fallback.
           - FALLBACK: If NO specific condo unit number is found, use the House Number.
           - WARNING: Do NOT extract Zip Codes (5 digits), Phone Numbers, Soi/Road numbers.
           - STRIP labels like "แขวง", "เขต", "จ.", "ถ.". Do NOT include province/district.
           - Format Preference: "X/Y" is highly likely to be the correct Room Number.

        3. Tracking Number (รหัสขนส่ง):
           - Barcode number starting with "TH", "7C", etc., or under the main barcode.
        
        4. Logistics Company (บริษัทขนส่ง):
           - Identify from logo/header (SPX, Flash, J&T, Kerry, Post).

        Output Format:
        Return ONLY valid JSON:
        {
          "recipient_name": "Recipient Name",
          "room_number": "Unit/Room Number",
          "tracking_number": "Tracking Number",
          "transport": "Logistics Company",
          "is_label": true,
          "reason_if_not": ""
        }
        
        CRITICAL RULES:
        1. "is_label" must be TRUE ONLY if you see a clear logistics label (e.g. Courier logo, Recipient name, Room number).
        2. If the image is blurry, random, or not a parcel label, set "is_label": false and provide "reason_if_not" (Thai).
        3. If it is a parcel but NO recipient name or room number is visible, set "is_label": false.
        """
        
        # New Google GenAI SDK (v1) expects specific structures or Part objects
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(data=image_data, mime_type='image/jpeg')
            ]
        )
        
        # Clean markdown json
        txt = response.text.strip()
        if txt.startswith("```json"):
            txt = txt[7:]
        if txt.endswith("```"):
            txt = txt[:-3]
            
        import json
        return json.loads(txt.strip())
    except Exception as e:
        print(f"AI Label Analysis Error: {e}")
        return None

def check_match(scanned_data, user_profile):
    """
    Robust comparison between scanned data and user profile.
    Returns: {
        "is_match": bool,
        "reason": str,
        "matched_fields": list,
        "ocr_details": dict
    }
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

    def normalize_name(name_str):
        if not name_str or name_str == "N/A": return ""
        # Remove common titles and spaces
        s = str(name_str).strip().lower()
        for title in ["คุณ", "mr.", "ms.", "mrs.", "miss", "นาย", "นาง", "นางสาว"]:
            s = s.replace(title, "")
        return s.replace(" ", "")

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

    # Final Decision: BOTH must nominally match or be strongly indicated
    # However, sometimes scanning misses one but gets the other perfectly.
    # We require at least ONE strong match and the other not being a HARD mismatch.
    
    is_match = room_match and name_match
    
    if is_match:
        reason = "ข้อมูลถูกต้อง ตรงกับฐานข้อมูล"
    elif room_match:
        reason = "พบเลขห้องที่ถูกต้อง แต่ชื่อผู้รับไม่ชัดเจน"
        # We might allow if room is very certain? Requirement says check both.
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
    Returns: (intent, selection_text)
    
    Examples:
    - "ขอรับนอกเวลา45632" -> ('register_outside', '45632')
    - "ยกเลิก ชิ้น1" -> ('cancel', 'ชิ้น1')  
    - "ลงทะเบียน" -> ('register_outside', None)
    - "1-3" -> ('pick_parcel', '1-3')
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
        import json
        result = json.loads(res.text.strip().replace('```json', '').replace('```', '').strip())
        
        intent = result.get('intent', 'general').lower()
        selection = result.get('selection')
        
        # Normalize null values
        if selection in ['null', 'None', '', 'none']:
            selection = None
            
        valid_intents = ['register_outside', 'check_parcel', 'pick_parcel', 'cancel', 'general']
        if intent not in valid_intents:
            intent = 'general'
            
        print(f"🔍 Intent: {intent}, Selection: {selection}")
        return (intent, selection)
        
    except Exception as e:
        print(f"Intent Extraction Error: {e}")
        # Fallback: try simple pattern matching
        import re
        text_lower = text.lower()
        
        # Check for numbers
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
    """
    Legacy compatibility wrapper - extracts only intent.
    """
    intent, _ = extract_intent_and_selection(text)
    return intent

def generate_chat_response(user_text, user_context={}):
    """
    Generates a response using Gemini + RAG + Chat History.
    """
    try:
        line_user_id = user_context.get('line_user_id')
        
        # 1. Fetch Chat History (Last 10 turns)
        history_context = ""
        if line_user_id:
            history = list(chat_history_col.find(
                {"line_user_id": line_user_id}
            ).sort("timestamp", -1).limit(10))
            
            # Reverse to get chronological order
            history.reverse()
            
            if history:
                history_text = []
                for h in history:
                    role_label = "User" if h['role'] == 'user' else "AI"
                    history_text.append(f"{role_label}: {h['message']}")
                history_context = "\n".join(history_text)
            else:
                history_context = "No previous history."
        
        # 2. RAG Step (Knowledge Retrieval)
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
    Comprehensive parcel selection extraction supporting:
    1. Pure numbers: "1 2 3" or "1"
    2. Comma-separated: "1,2,3" or "1, 2, 3"
    3. Ranges: "1-2", "2-4", "หนึ่งถึงสาม"
    4. Thai words: "ชิ้นหนึ่ง", "ชิ้นสอง"
    5. Mixed: "ชิ้น1และสอง", "ชิ้นสองและ3"
    6. With typos: corrections handled by AI
    7. PIN+Index: "ชิ้น1และรหัส65489", "รหัส45689และชิ้น3"
    """
    try:
        import re
        
        print(f"🔍 extract_selection_ids called with text: '{text}'")
        
        # Pre-format parcels for reference
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
        
        # Check if contains any Thai characters
        has_thai = bool(re.search(r'[\u0E00-\u0E7F]', text_clean))
        
        # Strategy 1: Pure number handling (ONLY if NO Thai text)
        if not has_thai:
            print("📊 Using regex for pure number input")
            
            # Handle ranges: "1-3", "2-4"
            range_match = re.match(r'^(\d+)\s*-\s*(\d+)$', text_clean)
            if range_match:
                start_idx = int(range_match.group(1))
                end_idx = int(range_match.group(2))
                for idx in range(start_idx, end_idx + 1):
                    if idx in parcel_by_index:
                        selected_pins.append(parcel_by_index[idx])
                print(f"✅ Range detected: {selected_pins}")
                return selected_pins
            
            # Handle comma-separated: "1,2,3" or "1, 2, 3"
            if ',' in text_clean:
                parts = re.split(r'[,\s]+', text_clean)
                for part in parts:
                    if part.isdigit():
                        idx = int(part)
                        if idx in parcel_by_index:
                            selected_pins.append(parcel_by_index[idx])
                print(f"✅ Comma-separated detected: {selected_pins}")
                return selected_pins if selected_pins else []
            
            # Handle space-separated: "1 2 3"
            if ' ' in text_clean:
                parts = text_clean.split()
                for part in parts:
                    if part.isdigit():
                        num = int(part)
                        # If it's a small number (1-9), treat as index
                        if 1 <= num <= len(parcels):
                            if num in parcel_by_index:
                                selected_pins.append(parcel_by_index[num])
                if selected_pins:
                    print(f"✅ Space-separated detected: {selected_pins}")
                    return selected_pins
            
            # Handle pure digits (no spaces): "123" or "1" or "12345"
            if text_clean.isdigit():
                digits = text_clean
                # Rule: 5+ digits = PIN, 1-4 digits = separate indexes
                if len(digits) >= 5:
                    # Treat as PIN
                    if digits in parcel_by_pin:
                        print(f"✅ PIN detected: {digits}")
                        return [digits]
                    print(f"⚠️ PIN {digits} not found")
                    return []
                else:
                    # Treat each digit as index: "123" -> [1,2,3]
                    for digit_char in digits:
                        idx = int(digit_char)
                        if idx in parcel_by_index:
                            selected_pins.append(parcel_by_index[idx])
                    print(f"✅ Sequential digits detected: {selected_pins}")
                    return selected_pins if selected_pins else []
        
        # Strategy 2: Use AI for Thai text, mixed inputs, or complex cases
        print("🤖 Using AI for complex input")
        info_str = "\n".join(parcel_info)
        
        prompt = f"""
        User wants to select parcels from this list:
        {info_str}
        
        User input: "{text}"
        
        TASK: Extract ALL selected parcels and return their PIN codes.
        
        HANDLE THESE FORMATS:
        1. Pure numbers: "1" -> Index 1, "1 2 3" -> Indexes 1,2,3
        2. Comma-separated: "1,2,3" or "1, 2, 3" -> Indexes 1,2,3
        3. Ranges: "1-2" or "2-4" -> Indexes in range
        4. Thai numbers: "หนึ่ง"=1, "สอง"=2, "สาม"=3, "สี่"=4, "ห้า"=5
        5. Thai ranges: "หนึ่งถึงสาม" or "ชิ้นหนึ่งถึงสาม" -> Indexes 1,2,3
        6. Mixed: "ชิ้น1และสอง" -> Indexes 1,2
        7. CORRECT TYPOS: "หนึง่"->1, "สอว"->2, "ชิ้นสองเเละ3"->"2,3"
        8. PIN codes: If text contains 5+ consecutive digits, treat as PIN
        9. PIN+Index mix: "ชิ้น1และรหัส65489" -> Index 1 + PIN 65489
        
        CRITICAL RULES:
        - Return the actual PIN codes from the list, NOT index numbers
        - For index N, find the PIN at that position
        - Be flexible with spacing and Thai spelling errors
        - If nothing matches, return empty array
        
        OUTPUT FORMAT: Return ONLY a valid JSON array of PIN strings.
        Examples: 
        - ["1234"] for single item
        - ["1234", "5678", "9012"] for multiple items
        - [] if nothing found
        
        DO NOT include any explanation, ONLY the JSON array.
        """
        
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        
        # Clean markdown
        txt = res.text.strip()
        print(f"🤖 AI Response: {txt}")
        
        if txt.startswith("```json"): txt = txt[7:]
        if txt.startswith("```"): txt = txt[3:]
        if txt.endswith("```"): txt = txt[:-3]
        txt = txt.strip()
        
        # Handle empty or invalid responses
        if not txt or txt.lower() == "none" or txt == "null":
            print("⚠️ AI returned empty response")
            return []
        
        import json
        selected_pins = json.loads(txt)
        
        if isinstance(selected_pins, list):
            result = [str(p) for p in selected_pins]
            print(f"✅ AI extraction successful: {result}")
            return result
        else:
            print(f"⚠️ AI returned non-list: {selected_pins}")
            return []
            
    except json.JSONDecodeError as e:
        print(f"❌ JSON Parse Error: {e}, Response was: {txt if 'txt' in locals() else 'N/A'}")
        return []
    except Exception as e:
        print(f"❌ Extraction Error: {e}")
        return []

