from google import genai
from ..config import Config
from .db import kb_col
import re

client = genai.Client(api_key=Config.GEMINI_API_KEY)
MODEL_NAME = 'gemini-2.0-flash'

CHAT_SYSTEM_PROMPT = """
You are "Nong Bot Niti", a helpful Condo Assistant.
Personality: Polite, Human-like, Empathetic.
Role: Answer questions about condo rules using provided Context.
Rules:
1. Only answer based on Context.
2. If Context has Parcel info, show it EXACTLY.
3. If no info, say you don't know politely.
4. Do NOT verify parcels unless User uploads a photo (which is handled separately).
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

def retrieve_knowledge(query, limit=3):
    """
    Search KB using keywords and text search.
    """
    try:
        keywords = extract_keywords(query)
        keyword_str = " ".join(keywords)
        print(f"RAG Search Keywords: {keyword_str}")
        
        # 1. Mongo Text Search (Requires Index)
        try:
            cursor = kb_col.find(
                {"$text": {"$search": keyword_str}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(limit)
            results = list(cursor)
        except Exception as e:
            print(f"Text search failed (index might be missing): {e}")
            results = []
            
        # 2. Fallback: Regex if no results
        if not results:
            regex_queries = [{"question": {"$regex": k, "$options": "i"}} for k in keywords]
            if regex_queries:
                 results = list(kb_col.find({"$or": regex_queries}).limit(limit))
                 
        return results
    except Exception as e:
        print(f"Retrieve Knowledge Error: {e}")
        return []

def analyze_parcel_label(image_data):
    """
    Analyze image data (bytes or object) to find Owner Name and Room Number.
    """
    try:
        prompt = """
        Analyze this parcel label image.
        Extract the following ONLY in JSON format:
        {
            "name": "found name (Thai or English)",
            "room_number": "found room number (digits)",
            "tracking_number": "found tracking number",
             "is_label": boolean (true if it looks like a parcel label)
        }
        If fields are missing, use null.
        """
        
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[prompt, image_data] 
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
        
    scanned_name = str(scanned_data.get('name') or "").replace(" ", "")
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
    Generates a response using Gemini + RAG.
    """
    try:
        # RAG Step
        docs = retrieve_knowledge(user_text)
        if docs:
            kb_context = "\n".join([f"Q: {d.get('question','')}\nA: {d.get('answer','')}" for d in docs])
        else:
            kb_context = "No specific rules found in database."
            
        user_info = f"User: {user_context.get('first_name','Guest')} Room: {user_context.get('room_number','-')}"
        
        full_prompt = f"""
        {CHAT_SYSTEM_PROMPT}
        
        [USER INFO]
        {user_info}
        
        [KNOWLEDGE BASE]
        {kb_context}
        
        [USER QUERY]
        {user_text}
        
        Answer (Answer normally as a helpful assistant. Do NOT use Block Cards here, just text):
        """
        
        res = client.models.generate_content(model=MODEL_NAME, contents=full_prompt)
        return res.text.strip()
    except Exception as e:
        print(f"Gen Chat Error: {e}")
        return "ขออภัยค่ะ น้องบอตกำลังประมวลผลข้อมูล โปรดรอสักครู่หรือลองใหม่ภายหลังค่ะ"

