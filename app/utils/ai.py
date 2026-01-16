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
Your goal: Provide accurate, helpful, and natural-sounding answers based on the provided context.

Rules for Interaction:
1. **Context Priority**: Use the [CONDO DATABASE] for rules, hours, and contacts.
2. **Conversation Flow**: Use [CHAT HISTORY] to maintain context. If the user asks "What did I just say?" or "Summarize", refer to the history.
3. **Accuracy**: Do not hallucinate. If info isn't in context or history, say you don't know politely.
4. **Tone**: Human-like, empathetic, and professional (Thai Language). Use "ค่ะ/ครับ" as appropriate (default to polite "ค่ะ").
5. **Summarization**: If the user asks for a summary of long instructions, provide a bulleted list.
6. **Room Info**: If the history or context contains the user's room number, remember it.
7. **User Addressing**: When referring to the user by name, ALWAYS use the format: " คุณ[Name] " (ensure there is a space before 'คุณ' and a space after the name). Example: "สวัสดีค่ะ คุณสมชาย มีอะไรให้ช่วยไหมคะ"
"""

def extract_keywords(text):
    """Deepmind: Extract keywords for RAG."""
    try:
        prompt = (
            f"Analyze text: '{text}'\n"
            "Extract 2-3 Thai keywords for searching condo rulebook.\n"
            "Focus on: appliances, rules, locations.\n"
            "Return only whitespace-separated keywords."
        )
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        # Handle case where AI might be chatty
        return res.text.strip().split()
    except Exception as e:
        print(f"AI Keyword Error: {e}")
        return text.split()

def retrieve_knowledge(query, limit=5):
    """
    Search KB using keywords and text search on topic, content, and tags.
    """
    try:
        keywords = extract_keywords(query)
        keyword_str = " ".join(keywords)
        print(f"RAG Search Keywords: {keyword_str}")
        
        # 1. Mongo Text Search
        try:
            cursor = kb_col.find(
                {"$text": {"$search": keyword_str}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(limit)
            results = list(cursor)
        except Exception as e:
            print(f"Text search failed: {e}")
            results = []
            
        # 2. Fallback: Regex on topic, content, and tags
        if not results:
            regex_or = []
            for k in keywords:
                regex_or.extend([
                    {"topic": {"$regex": k, "$options": "i"}},
                    {"content": {"$regex": k, "$options": "i"}},
                    {"tags": {"$regex": k, "$options": "i"}}
                ])
            if regex_or:
                 results = list(kb_col.find({"$or": regex_or}).limit(limit))
                 
        return results
    except Exception as e:
        print(f"Retrieve Knowledge Error: {e}")
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
           - Look for the text after "ผู้รับ (TO)" or just "TO".
           - Extract the full name strictly in Thai (or English if Thai is absent).
           - Ignore titles like "คุณ" if possible, but keep the name complete.

        2. House/Room Number (เลขห้อง/เลขที่บ้าน):
           - Look at the address section under the Recipient Name.
           - Extract the primary house or unit number, which usually contains digits and a slash (e.g., 28/548, 222/1, 730/541).
           - Do NOT extract the postal code here.

        3. Tracking Number (รหัสขนส่ง):
           - Look for the barcode number labelled as "TH..." or under the main barcode.
           - For Shopee Xpress (SPX), it usually starts with "TH".
           - Do NOT confuse it with "Shopee Order No." (which is different).
           - Example format: TH2654310236651.

        4. Logistics Company (บริษัทขนส่ง):
           - Identify the logo or text at the top header (e.g., SPX Express, Kerry, J&T, Flash).
           - In these images, it is likely "SPX Express".

        Output Format:
        Return the result strictly in JSON format as follows:
        {
          "recipient_name": "Recipient Name",
          "room_number": "Unit/Room Number",
          "tracking_number": "Tracking Number",
          "transport": "Logistics Company",
          "is_label": true
        }
        
        If the image is NOT a parcel label, set "is_label" to false and other fields to "N/A".
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
            
        user_info = f"User Status: {user_context.get('first_name','Guest')} (Room {user_context.get('room_number','-')})"
        
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

