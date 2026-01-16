"""
User Service Module - Smart Condo Backend
Handles user management and registration
"""
import datetime
from database import users_col

def get_or_create_user(user_id, platform="line", display_name=None, picture_url=None):
    """
    Get existing user or create new one
    Args:
        user_id: LINE User ID
        platform: 'line' or 'web'
        display_name: User's display name
        picture_url: Profile picture URL
    Returns:
        dict: User document
    """
    try:
        user = users_col.find_one({"line_user_id": user_id})
        
        update_data = {
            "last_active": datetime.datetime.utcnow(),
            "platform": platform
        }
        if display_name:
            update_data["display_name"] = display_name
        if picture_url:
            update_data["picture_url"] = picture_url

        if not user:
            # Create new user
            new_user = {
                "line_user_id": user_id,
                "first_name": None,
                "last_name": None, 
                "room_number": None,
                "phone_number": None,
                "chat_history": [],
                "display_name": display_name if display_name else "Unknown",
                "picture_url": picture_url,
                **update_data
            }
            users_col.insert_one(new_user)
            print(f"✅ Created new user: {user_id}")
            return new_user
        else:
            # Update existing user
            users_col.update_one(
                {"line_user_id": user_id},
                {"$set": update_data}
            )
            return users_col.find_one({"line_user_id": user_id})
            
    except Exception as e:
        print(f"❌ Get/Create User Error: {e}")
        return None

def is_registered(user):
    """
    Check if user has completed registration
    Required fields: first_name, last_name, room_number, phone_number
    """
    if not user:
        return False
    
    required_fields = ['first_name', 'last_name', 'room_number', 'phone_number']
    
    for field in required_fields:
        value = user.get(field)
        if not value or str(value).strip() == '' or str(value).strip().lower() == 'none':
            return False
    
    return True

def register_user(user, room, first_name, last_name, phone):
    """
    Register user with room and personal information
    Args:
        user: User document
        room: Room number
        first_name: First name
        last_name: Last name
        phone: Phone number
    Returns:
        (success: bool, message: str)
    """
    try:
        # Check for duplicate phone number
        existing_phone = users_col.find_one({
            "phone_number": phone,
            "line_user_id": {"$ne": user['line_user_id']}
        })
        if existing_phone:
            return False, f"⛔ เบอร์ {phone} มีผู้ใช้แล้วค่ะ"
        
        # Check for duplicate room
        existing_room = users_col.find_one({
            "room_number": room,
            "line_user_id": {"$ne": user['line_user_id']}
        })
        if existing_room:
            return False, f"⛔ ห้อง {room} มีผู้ใช้แล้วค่ะ"
        
        # Update user registration
        users_col.update_one(
            {"line_user_id": user['line_user_id']},
            {"$set": {
                "first_name": first_name,
                "last_name": last_name,
                "room_number": room,
                "phone_number": phone
            }}
        )
        
        message = (
            f"✅ ลงทะเบียนสำเร็จ!\n"
            f"🏠 ห้อง: {room}\n"
            f"👤 ชื่อ: {first_name} {last_name}\n"
            f"📞 เบอร์: {phone}\n\n"
            f"ตอนนี้คุณสามารถใช้งานแชตบอตได้เต็มรูปแบบแล้วค่ะ 🎉"
        )
        
        print(f"✅ User registered: Room {room}, {first_name} {last_name}")
        return True, message
        
    except Exception as e:
        print(f"❌ Register User Error: {e}")
        return False, "เกิดข้อผิดพลาดในการลงทะเบียนค่ะ"

def find_user_by_room_or_name(room_number=None, recipient_name=None):
    """
    Find user by room number or recipient name
    Returns: User document or None
    """
    try:
        query = {}
        
        if room_number and room_number != "-":
            # Normalize room number
            normalized_room = str(room_number).strip().replace("ห้อง", "").strip()
            query["$or"] = [
                {"room_number": normalized_room},
                {"room_number": f"ห้อง {normalized_room}"},
                {"room_number": f"Room {normalized_room}"},
                {"room_number": {"$regex": f"^{normalized_room}$", "$options": "i"}}
            ]
        
        if recipient_name and recipient_name != "-":
            name_query = {
                "$or": [
                    {"display_name": {"$regex": f".*{recipient_name}.*", "$options": "i"}},
                    {"first_name": {"$regex": f".*{recipient_name}.*", "$options": "i"}},
                    {"last_name": {"$regex": f".*{recipient_name}.*", "$options": "i"}}
                ]
            }
            
            if query:
                query = {"$and": [query, name_query]}
            else:
                query = name_query
        
        if not query:
            return None
        
        user = users_col.find_one(query)
        return user
        
    except Exception as e:
        print(f"❌ Find User Error: {e}")
        return None

def update_chat_history(uid, role, message, platform="line", image_url=None):
    """
    Update user's chat history (keep last 10 messages)
    """
    try:
        if role == 'assistant':
            role = 'model'
        
        entry = {
            "role": role,
            "parts": [message],
            "timestamp": datetime.datetime.utcnow()
        }
        if image_url:
            entry["image_url"] = image_url

        users_col.update_one(
            {"line_user_id": uid},
            {"$push": {"chat_history": {"$each": [entry], "$slice": -10}}}
        )
        
        return True
    except Exception as e:
        print(f"❌ Update Chat History Error: {e}")
        return False

def get_chat_history(uid):
    """Get user's chat history for Gemini context"""
    try:
        user = users_col.find_one({"line_user_id": uid})
        history = []
        
        if user and "chat_history" in user:
            for msg in user["chat_history"]:
                role = msg.get("role")
                raw_parts = msg.get("parts")
                
                if not raw_parts:
                    raw_parts = [msg.get("text", "")]
                
                if role == "assistant":
                    role = "model"
                
                formatted_parts = []
                for part in raw_parts:
                    if isinstance(part, str):
                        formatted_parts.append({"text": part})
                    else:
                        formatted_parts.append(part)
                
                if role and formatted_parts:
                    history.append({"role": role, "parts": formatted_parts})
        
        return history
    except Exception as e:
        print(f"❌ Get Chat History Error: {e}")
        return []
