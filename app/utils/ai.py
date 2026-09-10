from google import genai
from google.genai import types
from openai import OpenAI
from ..config import Config
from .db import kb_col, chat_history_col
import re
import datetime
import base64
import json
from .lookup import normalize_name

# --- Gemini (ใช้เฉพาะ Embedding สำหรับ Vector Search) ---
gemini_client = genai.Client(api_key=Config.GEMINI_API_KEY)
EMBEDDING_MODEL = 'gemini-embedding-001'

# --- Typhoon LLM (Chat, Intent, Keywords) ---
typhoon_client = OpenAI(
    api_key=Config.TYPHOON_API_KEY,
    base_url="https://api.opentyphoon.ai/v1"
)
TYPHOON_LLM_MODEL = "typhoon-v2.5-30b-a3b-instruct"

# --- Typhoon OCR (อ่านตัวอักษรจากภาพ) ---
typhoon_ocr_client = OpenAI(
    api_key=Config.TYPHOON_API_KEY,
    base_url="https://api.opentyphoon.ai/v1"
)
TYPHOON_OCR_MODEL = "typhoon-ocr"

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
    """Enhanced keyword extraction with typo correction and intent expansion (Typhoon LLM)."""
    typo_map = {
        'หอวข้าว': 'หาอาหาร', 'หอว': 'หา', 'หวิข้าว': 'หิวข้าว',
        'เซเวน': 'เซเว่น', 'ร้านาหาร': 'ร้านอาหาร',
        'ส่วนกลาง': 'สิ่งอำนวยความสะดวก'
    }
    try:
        corrected_text = text
        for typo, correct in typo_map.items():
            corrected_text = corrected_text.replace(typo, correct)
        
        prompt = f"""วิเคราะห์ข้อความของผู้ใช้ แก้คำผิดภาษาไทย และสกัด 3-5 คำสำคัญสำหรับค้นหาในฐานข้อมูลคอนโด

ตัวอย่าง:
- "หิวข้าว"/"หาอาหาร" → อาหาร ร้านอาหาร เซเว่น ร้านค้า
- "จอดรถ"/"ที่จอด" → จอดรถ ที่จอดรถ ลานจอด
- "ฟิตเนส"/"สระน้ำ" → สิ่งอำนวยความสะดวก ฟิตเนส ออกกำลังกาย สระว่ายน้ำ

ข้อความผู้ใช้: "{corrected_text}"

ตอบด้วยคำสำคัญเท่านั้น คั่นด้วยช่องว่าง:"""
        
        res = typhoon_client.chat.completions.create(
            model=TYPHOON_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.1
        )
        keywords = res.choices[0].message.content.strip().split()
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
    (ยังคงใช้ Gemini Embedding เนื่องจาก Typhoon ไม่มี Embedding API ในขณะนี้)
    """
    try:
        result = gemini_client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config={'output_dimensionality': 768}
        )
        return result.embeddings[0].values
    except Exception as e:
        print(f"❌ Embedding Error: {e}")
        return []

def retrieve_knowledge(query, limit=15):
    """Enhanced hybrid search strategy with PDF prioritization and holistic search."""
    try:
        # 0. Special Handling: Identity Questions (Who/Where/What Project)
        # If user asks about the place, FORCE include Page 1 of all PDFs (usually covers)
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
                            "numCandidates": 100,  # Scan more candidates
                            "limit": 20            # Return more vector results
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
            ).sort([("score", {"$meta": "textScore"})]).limit(20) # Significantly increased limit
            text_results = list(cursor)
        except Exception as e:
             pass
             
        # 4. Force Page 1 Injection (if identity question)
        page_one_results = []
        if force_page_one:
            print("🚀 Identity Question Detected: Injecting PDF Covers...")
            # Fetch Page 1 from all PDFs
            page_one_results = list(kb_col.find({"type": "pdf", "page": 1}).limit(5))
            
        # Merge Strategy: 
        # 1. Page 1s (if relevant)
        # 2. PDFs (Text & Vector)
        # 3. Everything else
        
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
                
                # Cap at 15 distinct chunks to provide broad context
                if len(results) >= 15:
                    break
        
        return results
    except Exception as e:
        print(f"❌ RAG Error: {e}")
        return []

def analyze_parcel_label(image_data):
    """
    วิเคราะห์ป้ายพัสดุด้วย Typhoon OCR + Typhoon LLM (2 ขั้นตอน):
    Step 1: Typhoon OCR อ่านตัวอักษรทั้งหมดจากภาพ (raw text)
    Step 2: Typhoon LLM แปลง raw text เป็น structured JSON
    """
    try:
        # --- Step 1: Typhoon OCR - อ่านตัวอักษรจากภาพ ---
        print("📸 Sending image to Typhoon OCR...")
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        ocr_response = typhoon_ocr_client.chat.completions.create(
            model=TYPHOON_OCR_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "อ่านและถอดความข้อความทุกตัวอักษรที่เห็นในภาพนี้ให้ครบถ้วน แม่นยำตามต้นฉบับ ทั้งภาษาไทย ตัวเลข และภาษาอังกฤษทั้งหมด รักษาตำแหน่งสระ-วรรณยุกต์ให้ถูกต้อง (เช่น สระอุ สระอู อักษร อ และ ฮ) และแยกแยะตัวเลขกับตัวอักษรภาษาอังกฤษอย่างแม่นยำ (เช่น เลข 1 กับตัว I หรือ l, เลข 0 กับตัว O)"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1000,
            temperature=0,
            top_p=0.1,
            extra_body={"repetition_penalty": 1.2}
        )
        
        raw_ocr_text = ocr_response.choices[0].message.content.strip()
        print(f"🔤 Typhoon OCR raw text: {raw_ocr_text[:200]}...")
        
        if not raw_ocr_text:
            print("⚠️ OCR returned empty text")
            return {"is_label": False, "recipient_name": "N/A", "room_number": "N/A", "transport": "N/A", "tracking_number": "N/A"}
        
        # --- Step 2: Typhoon LLM - แปลง raw text เป็น JSON ---
        print("🧠 Sending OCR text to Typhoon LLM for JSON extraction...")
        
        llm_prompt = f"""คุณคือผู้เชี่ยวชาญสกัดข้อมูลจากป้ายพัสดุภาษาไทย
วิเคราะห์ข้อความ OCR ต่อไปนี้และสกัดข้อมูลป้ายพัสดุ:

[OCR TEXT]
{raw_ocr_text}

[กฎการสกัดข้อมูล]
1. transport (บริษัทขนส่ง) - ดูจากโลโก้/ชื่อบริษัทในข้อความ:
   - "SPX", "Shopee", "Shopee Express" → "SPX EXPRESS"
   - "Flash", "Flazz", "FLASH" → "FLASH EXPRESS"
   - "Kerry", "KEX" → "KEX EXPRESS"
   - "J&T" → "J&T EXPRESS"
   - "Thailand Post", "ปณ", "EMS", "ไปรษณีย์" → "THAILAND POST"
   - "DHL" → "DHL"
   - "Ninja", "NinjaVan" → "NINJA VAN"
   - "Lazada", "LEX" → "LAZADA EXPRESS"
   - "Best" → "BEST EXPRESS"
   - "SCG" → "SCG EXPRESS"
   - "Nim" → "NIM EXPRESS"
   - ถ้าไม่พบ → "N/A"

2. recipient_name (ชื่อผู้รับ) - หาจากคำว่า "ผู้รับ" หรือ "TO:":
   - ตัดคำนำหน้า (นาย/นาง/นางสาว/คุณ) ออก
   - ตรวจสอบคำผิดที่อาจเกิดจาก OCR เช่น สับสนระหว่าง "อ" กับ "ฮ" หรือสระอุ/สระอู/วรรณยุกต์ที่ตกหล่น ให้แก้ไขสะกดเป็นชื่อ-สกุลภาษาไทยที่ถูกต้อง
   - ถ้าไม่พบ → "N/A"

3. room_number (เลขห้อง) - มักอยู่หลังชื่อผู้รับ หรือบรรทัดถัดไป:
   - รูปแบบ: XX/YY หรือตัวเลขล้วน
   - หากมีตัว "I" หรือ "l" ปนในตัวเลข ให้แปลงเป็นเลข "1"
   - อย่าสับสนกับราคาหรือ COD
   - ถ้าไม่พบ → "N/A"

4. tracking_number (เลขพัสดุ) - รหัสใต้บาร์โค้ด (TH..., KER..., SPX..., KEX...):
   - หากมีตัว "I" หรือ "l" ปะปนอยู่ท่ามกลางตัวเลข ให้แก้เป็นเลข "1" (เช่น TH0I... -> TH01...)
   - ถ้าไม่พบ → "N/A"

5. is_label - true ถ้าข้อความมีลักษณะป้ายพัสดุ, false ถ้าไม่ใช่

ตอบเป็น JSON เท่านั้น ห้ามอธิบายเพิ่ม:
{{"recipient_name": "...", "room_number": "...", "transport": "...", "tracking_number": "...", "is_label": true/false}}"""
        
        llm_response = typhoon_client.chat.completions.create(
            model=TYPHOON_LLM_MODEL,
            messages=[{"role": "user", "content": llm_prompt}],
            max_tokens=300,
            temperature=0
        )
        
        result_text = llm_response.choices[0].message.content.strip()
        # ทำความสะอาด markdown code block ถ้ามี
        result_text = result_text.replace('```json', '').replace('```', '').strip()
        
        result = json.loads(result_text)
        print(f"✅ Typhoon LLM parsed: {result}")
        return result
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON Parse Error: {e}")
        return None
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Typhoon OCR/LLM Error: {error_msg}")
        if "401" in error_msg or "Unauthorized" in error_msg:
            return {"error": "unauthorized", "message": "Typhoon API Key ไม่ถูกต้องหรือยังไม่ได้ตั้งค่า"}
        if "429" in error_msg or "rate_limit" in error_msg.lower():
            return {"error": "rate_limit", "message": "Typhoon API Rate Limit Exceeded"}
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

    # Note: normalize_name is now imported from .lookup

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
    Extract both intent and embedded selection from user input (Typhoon LLM).
    Returns: (intent, selection_text)
    
    Examples:
    - "ขอรับนอกเวลา45632" -> ('register_outside', '45632')
    - "ยกเลิก ชิ้น1" -> ('cancel', 'ชิ้น1')  
    - "ลงทะเบียน" -> ('register_outside', None)
    - "1-3" -> ('pick_parcel', '1-3')
    """
    try:
        prompt = f"""วิเคราะห์ข้อความภาษาไทยเพื่อหา intent และ selection (ตัวเลข/PIN) ที่ฝังอยู่

[กฎ Intent]
- 'register_outside': ลงทะเบียน, รับนอกเวลา, ขอรับนอกเวลา
- 'cancel': ยกเลิก, ย้ายกลับ, ยกเลิกนอกเวลา
- 'pick_parcel': ตัวเลข/ช่วง เช่น 1, 1-3, ชิ้น2, รหัส1234
- 'check_parcel': เช็ก, ดูพัสดุ, มีพัสดุไหม
- 'general': อื่นๆ

ข้อความ: "{text}"

ถ้ามีทั้ง intent และ selection (เช่น "ขอรับนอกเวลา45632") ให้สกัดทั้งคู่
ถ้ามีแค่ intent (เช่น "ลงทะเบียน") selection = null
ถ้ามีแค่ตัวเลข (เช่น "45632") intent = 'pick_parcel'

ตอบเป็น JSON เท่านั้น:
{{"intent": "register_outside|cancel|pick_parcel|check_parcel|general", "selection": "ตัวเลขหรือ null"}}"""

        res = typhoon_client.chat.completions.create(
            model=TYPHOON_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.1
        )
        result_text = res.choices[0].message.content.strip().replace('```json', '').replace('```', '').strip()
        result = json.loads(result_text)
        
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
        
        # 1. Use Active Context from User Profile (Fast & Relevant)
        history_context = ""
        # The history comes directly from the user document slice we maintain
        raw_history = user_context.get('history', [])
        
        if raw_history:
            history_text = []
            for h in raw_history:
                # Interpret role
                role_label = "AI" if h.get('role') == 'assistant' else "User"
                msg = h.get('message', '')
                if msg:
                    history_text.append(f"{role_label}: {msg}")
            
            if history_text:
                history_context = "\n".join(history_text)
                print(f"📜 loaded {len(history_text)} turns from User Context")
            else:
                history_context = "No previous history."
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
        
        response = typhoon_client.chat.completions.create(
            model=TYPHOON_LLM_MODEL,
            messages=[{"role": "user", "content": full_prompt}],
            max_tokens=1000,
            temperature=0.4
        )
        return response.choices[0].message.content.strip()
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
        
        # Strategy 2: Use Typhoon LLM for Thai text, mixed inputs, or complex cases
        print("🤖 Using Typhoon LLM for complex input")
        info_str = "\n".join(parcel_info)
        
        prompt = f"""ผู้ใช้ต้องการเลือกพัสดุจากรายการนี้:
{info_str}

ข้อความผู้ใช้: "{text}"

สกัด PIN codes ของพัสดุที่เลือก รองรับรูปแบบ:
1. ตัวเลขล้วน: "1" → Index 1, "1 2 3" → Indexes 1,2,3
2. คั่นด้วยจุลภาค: "1,2,3" → Indexes 1,2,3
3. ช่วง: "1-2", "2-4" → Index ในช่วง
4. ตัวเลขไทย: "หนึ่ง"=1, "สอง"=2, "สาม"=3, "สี่"=4, "ห้า"=5
5. ช่วงภาษาไทย: "หนึ่งถึงสาม" → 1,2,3
6. ผสม: "ชิ้น1และสอง" → 1,2
7. แก้คำผิด: "หนึง่"→1, "สอว"→2
8. PIN 5+ หลัก: ถือว่าเป็น PIN code โดยตรง

คืนค่าเป็น JSON array ของ PIN strings เท่านั้น:
- ["12345"] สำหรับชิ้นเดียว
- ["12345", "67890"] สำหรับหลายชิ้น
- [] ถ้าไม่พบ

ห้ามอธิบาย ตอบแค่ JSON array:"""
        
        res = typhoon_client.chat.completions.create(
            model=TYPHOON_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1
        )
        
        # Clean markdown
        txt = res.choices[0].message.content.strip()
        print(f"🤖 Typhoon LLM Response: {txt}")
        
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

