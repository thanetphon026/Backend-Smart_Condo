from google import genai
from google.genai import types
from ..config import Config
from .db import kb_col, chat_history_col
import re
import datetime

client = genai.Client(api_key=Config.GEMINI_API_KEY)
MODEL_NAME = 'gemini-2.0-flash'

CHAT_SYSTEM_PROMPT = """
You are "Nong Bot Niti", a highly intelligent and polite Condo Assistant.
Your goal: Provide accurate, helpful, and natural-sounding answers based on context AND general knowledge.

Rules for Interaction:
1. **Context Priority**: Use the [CONDO DATABASE] for rules, hours, and contacts.
2. **General Knowledge Enhancement**: If the database has limited info (e.g., mentions "7-Eleven" but no menu details), use your GENERAL KNOWLEDGE to provide helpful suggestions (e.g., "7-Eleven typically has rice boxes, sandwiches, snacks, drinks").
3. **Intent Analysis**: Infer user intent even from typos or vague questions:
   - "หิวข้าว", "หาอาหาร", "หอวข้าว" → User wants food recommendations
   - "จอดรถ" → User asking about parking
   - "ออกกำลัง" → User asking about fitness facilities
4. **Conversation Flow**: Use [CHAT HISTORY] to maintain context. If the user asks "What did I just say?" or "Summarize", refer to the history.
5. **Accuracy**: Prioritize database info. Use general knowledge ONLY to enrich answers, not to contradict the database.
6. **Tone**: Human-like, empathetic, and professional (Thai Language). Use "ค่ะ/ครับ" as appropriate (default to polite "ค่ะ").
7. **Helpful Suggestions**: If the database mentions a facility/service (e.g., "มีร้านอาหาร", "มี 7-Eleven"), proactively suggest what's typically available there.
8. **Summarization**: If the user asks for a summary of long instructions, provide a bulleted list.
9. **Room Info**: If the history or context contains the user's room number, remember it for answering specific questions about their unit.
10. **User Addressing**: When referring to the user by name, ALWAYS use ONLY the format: " คุณ[Name] ". DO NOT include the room number in parentheses.
   Example: "สวัสดีค่ะ คุณสมชาย มีอะไรให้ช่วยไหมคะ" (Correct)
   Example: "สวัสดีค่ะ คุณ (101) สมชาย" (INCORRECT - DO NOT DO THIS)
"""

def extract_keywords(text):
    """Enhanced keyword extraction with typo correction and intent expansion."""
    try:
        # Common Thai typo corrections
        typo_map = {
            'หอวข้าว': 'หาอาหาร', 'หอว': 'หา', 'หวิข้าว': 'หิวข้าว',
            'เซเวน': 'เซเว่น', 'ร้านาหาร': 'ร้านอาหาร'
        }
        
        corrected_text = text
        for typo, correct in typo_map.items():
            corrected_text = corrected_text.replace(typo, correct)
        
        prompt = f"""Analyze: "{corrected_text}"
Extract 3-5 Thai keywords for condo knowledge base.

Infer intent and include related terms:
- "หิวข้าว"/"หาอาหาร" → อาหาร ร้านอาหาร เซเว่น ร้านค้า
- "จอดรถ" → จอดรถ ที่จอดรถ ลานจอด
- "ฟิตเนส" → ฟิตเนส ออกกำลังกาย สระว่ายน้ำ

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

def retrieve_knowledge(query, limit=8):
    """
    Enhanced search using keywords, fuzzy matching, and multiple strategies.
    """
    try:
        keywords = extract_keywords(query)
        keyword_str = " ".join(keywords)
        print(f"🔍 RAG Search Keywords: {keyword_str}")
        
        results = []
        
        # Strategy 1: MongoDB Text Search
        try:
            cursor = kb_col.find(
                {"$text": {"$search": keyword_str}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(limit)
            results = list(cursor)
            print(f"✅ Text search found: {len(results)} results")
        except Exception as e:
            print(f"⚠️ Text search failed: {e}")
        
        # Strategy 2: Fuzzy Regex Search (if text search fails or returns few results)
        if len(results) < 3:
            print("🔄 Trying fuzzy regex search...")
            regex_queries = []
            for kw in keywords:
                # Create fuzzy regex (allow for minor variations)
                regex_queries.extend([
                    {"topic": {"$regex": kw, "$options": "i"}},
                    {"content": {"$regex": kw, "$options": "i"}},
                    {"tags": {"$in": [kw]}}
                ])
            
            if regex_queries:
                fuzzy_results = list(kb_col.find({"$or": regex_queries}).limit(limit))
                print(f"✅ Fuzzy search found: {len(fuzzy_results)} results")
                
                # Merge without duplicates
                existing_ids = {str(r.get('_id')) for r in results}
                for fr in fuzzy_results:
                    if str(fr.get('_id')) not in existing_ids:
                        results.append(fr)
                        if len(results) >= limit:
                            break
        
        return results[:limit]
    except Exception as e:
        print(f"❌ Retrieve Knowledge Error: {e}")
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
           - Can be found: 1) Appended to name, 2) In address, 3) Floating near the top/right corner.
           - Usually contains a slash (/) e.g., 123/45, 9/123.
           - STRIP labels like "แขวง", "เขต", "จ.", "ถ." or "จังหวัด". Do NOT include the provincial/district address parts here.
           - Only extract the unit identifying number.

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
          "is_label": true
        }
        
        If not a label, set "is_label": false.
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
    Compare scanned data with user profile.
    Returns: (is_match: bool, reason: str)
    """
    if not scanned_data or not scanned_data.get('is_label'):
        return False, "Not a parcel label"
    
    scanned_room = str(scanned_data.get('room_number') or "").strip()
    user_room = str(user_profile.get('room_number') or "").strip()
    
    # Stricter with detailed details
    if scanned_room and user_room and (scanned_room in user_room or user_room in scanned_room):
        return True, "Room match"
        
    scanned_name = str(scanned_data.get('recipient_name') or "").replace(" ", "")
    user_name = (user_profile.get('first_name', '') + user_profile.get('last_name', '')).replace(" ", "")
    
    if scanned_name and user_name:
        if scanned_name in user_name or user_name in scanned_name:
            return True, "Name match"
            
    # Mismatch Details
    reason = f"Scanned Room: '{scanned_room}' vs User Room: '{user_room}'. Scanned Name: '{scanned_name}' vs User Name: '{user_name}'"
    return False, reason


def analyze_intent(text):
    """
    Classify user text into:
    - 'register_outside': Request to pick up after hours.
    - 'check_parcel': Asking if they have parcels.
    - 'pickup_confirm': Trying to confirm receipt (via text).
    - 'cancel': Cancel something.
    - 'general': General questions (RAG).
    """
    try:
        prompt = f"""
        Classify the intent of this text into EXACTLY ONE of these categories:
        [register_outside, check_parcel, cancel, general]
        
        Text: "{text}"
        
        Rules:
        - "ลงทะเบียนรับนอกเวลา", "รับของนอกเวลา", "not in time" -> register_outside
        - "มีพัสดุไหม", "ของมายัง", "เช็คพัสดุ" -> check_parcel
        - "ยกเลิก", "ไม่รับแล้ว" -> cancel
        - Everything else -> general
        
        Return ONLY the category name.
        """
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        intent = res.text.strip().lower()
        valid_intents = ['register_outside', 'check_parcel', 'cancel', 'general']
        return intent if intent in valid_intents else 'general'
    except:
        return 'general'

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
                f"Topic: {d.get('topic','-')}\nContent: {d.get('content','')}\nTags: {', '.join(d.get('tags',[]))}" 
                for d in docs
            ])
        else:
            kb_context = "No specific condo internal data found for this query."
            
        user_info = f"User Name: {user_context.get('first_name','Guest')}\nUser Room: {user_context.get('room_number','-')}"
        
        full_prompt = f"""
        {CHAT_SYSTEM_PROMPT}
        
        [CONDO DATABASE]
        {kb_context}
        
        [USER PROFILE]
        {user_info}
        
        [CHAT HISTORY]
        {history_context}
        
        [CURRENT USER MESSAGE]
        User: {user_text}
        
        Instruction: 
        1. Review the HISTORY to understand the flow.
        2. Answer the CURRENT MESSAGE based on DATABASE and HISTORY.
        3. If the user asks for a summary of history or earlier database facts, provide it clearly.
        4. Be precise. If the user asks about something mentioned 2 turns ago, answer correctly.
        
        AI Answer (Thai):
        """
        
        res = client.models.generate_content(model=MODEL_NAME, contents=full_prompt)
        return res.text.strip()
    except Exception as e:
        print(f"Gen Chat Error: {e}")
        return "ขออภัยค่ะ น้องบอตกำลังประมวลผลข้อมูล โปรดรอสักครู่หรือลองใหม่ภายหลังค่ะ"

