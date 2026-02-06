"""
User Lookup Utility
Provides functions for finding users based on parcel information with fuzzy matching.
"""

from .db import users_col, parcels_col


def normalize_room(room_str):
    """
    Normalize room number for comparison.
    Removes whitespace, common prefixes, Thai digits, and standardizes format.
    """
    if not room_str or room_str == "N/A":
        return None
        
    # Thai digits mapping
    thai_digits = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')
    
    # Convert to string, translate Thai digits, strip all whitespace
    normalized = str(room_str).translate(thai_digits).strip()
    normalized = "".join(normalized.split())
    
    # Remove common Thai/English prefixes
    normalized = normalized.replace("Room", "").replace("room", "").replace("ห้อง", "")
    
    # Remove leading zeros if any in the room parts
    if "/" in normalized:
        parts = normalized.split("/")
        normalized = "/".join([p.lstrip('0') if p != '0' else '0' for p in parts])
    else:
        normalized = normalized.lstrip('0') if normalized != '0' else '0'
        
    return normalized if normalized else None


def normalize_name(name_str):
    """
    Normalize name for comparison.
    Removes titles, whitespace, Thai tone marks, and converts to lowercase.
    """
    if not name_str or name_str == "N/A":
        return None
    
    import re
    # Thai tone marks and symbols: ่ ้ ๊ ๋ ็ ์ ํ ฺ
    thai_tones = r'[\u0e31\u0e34-\u0e3a\u0e47-\u0e4e]'
    
    # 1. Basic cleaning
    s = str(name_str).strip()
    
    # 2. Remove common titles
    titles = ["คุณ", "นาย", "นาง", "นางสาว", "เด็กชาย", "เด็กหญิง", "mr.", "ms.", "mrs.", "miss"]
    for t in titles:
        s = s.replace(t, "")
        
    # 3. Remove Thai tones/vowels that cause misreads
    s = re.sub(thai_tones, '', s)
    
    # 4. Remove all whitespace
    s = "".join(s.split())
    
    return s.lower() if s else None


def find_user_by_parcel_info(room_number=None, recipient_name=None):
    """
    Find user in database based on room number and/or recipient name.
    Uses efficient MongoDB queries:
    1. Exact room match
    2. Partial room match (starts with or ends with)
    3. Name matching (fuzzy regex)
    """
    room_normalized = normalize_room(room_number)
    name_normalized = normalize_name(recipient_name)
    
    print(f"🔍 Lookup - Room: '{room_number}' -> '{room_normalized}', Name: '{recipient_name}' -> '{name_normalized}'")
    
    # Strategy 1: Flexible Room Match (Regex-based for speed + accuracy)
    if room_normalized:
        # Create a regex that is flexible about common prefixes like "ห้อง" or "Room"
        # and whitespace, but focuses on the core digits and slashes
        clean_room = room_normalized.replace("/", r"\/")
        # Matches: "ห้อง 101/5", "Room 101/5", "101/5", etc.
        room_regex = f".*{clean_room}.*"
        user = users_col.find_one({"room_number": {"$regex": room_regex, "$options": "i"}})
        if user:
            print(f"✅ MATCH by room regex: {room_normalized}")
            return user
            
    # Strategy 2: If slashed room found, try matching just the part after slash
    if room_normalized and "/" in room_normalized:
        part_after = room_normalized.split("/")[-1]
        if len(part_after) >= 2:
            user = users_col.find_one({"room_number": {"$regex": part_after + "$", "$options": "i"}})
            if user:
                print(f"✅ MATCH by room suffix: {part_after}")
                return user
            
    # Strategy 3: Try name matching (improved for accuracy)
    if name_normalized and len(name_normalized) > 2:
        # 3.1 Try direct field regex (already fast)
        query = {
            "$or": [
                {"first_name": {"$regex": name_normalized, "$options": "i"}},
                {"last_name": {"$regex": name_normalized, "$options": "i"}},
                {"display_name": {"$regex": name_normalized, "$options": "i"}}
            ]
        }
        user = users_col.find_one(query)
        if user:
            print(f"✅ MATCH by direct name query: {name_normalized}")
            return user
            
        # 3.2 Try searching by First word only (if full name didn't match)
        # Often OCR misreads the last name but gets the first name right
        name_parts = name_normalized.split()
        if len(name_parts) > 0 and len(name_parts[0]) > 2:
            first_token = name_parts[0]
            user = users_col.find_one({
                "$or": [
                    {"first_name": {"$regex": first_token, "$options": "i"}},
                    {"display_name": {"$regex": first_token, "$options": "i"}}
                ]
            })
            if user:
                print(f"✅ MATCH by first name token: {first_token}")
                return user
            
        # 3.3 If still not found, try MongoDB TEXT SEARCH (Fast)
        try:
            # Clean for search
            text_query = name_normalized.replace("/", " ") 
            user = users_col.find_one(
                {"$text": {"$search": text_query}},
                {"score": {"$meta": "textScore"}}
            )
            if user:
                print(f"✅ MATCH by MongoDB Text Search: {name_normalized}")
                return user
        except Exception as te:
            print(f"⚠️ Text Search Error/Unavailable: {te}")

        # 3.4 Deep Fallback: Normalize EVERY name in DB and compare (only if above fails)
        print("🧠 Running Deep Name Fallback (Ignoring Tones)...")
        # Optimization: Only search users in the SAME room if room was found
        # This drastically reduces the number of users to check.
        search_filter = {}
        if room_normalized:
            search_filter = {"room_number": room_normalized}
        
        all_users = list(users_col.find(search_filter, {"first_name": 1, "last_name": 1, "display_name": 1, "room_number": 1}))
        
        # If no users in that room, search all (just in case)
        if room_normalized and not all_users:
             all_users = list(users_col.find({}, {"first_name": 1, "last_name": 1, "display_name": 1, "room_number": 1}))

        for u in all_users:
            fn = normalize_name(u.get('first_name', ''))
            ln = normalize_name(u.get('last_name', ''))
            dn = normalize_name(u.get('display_name', ''))
            full = (fn or '') + (ln or '')
            
            # Match against parts or full name
            if (fn and (name_normalized in fn or fn in name_normalized)) or \
               (ln and (name_normalized in ln or ln in name_normalized)) or \
               (dn and (name_normalized in dn or dn in name_normalized)) or \
               (full and (name_normalized in full or full in name_normalized)):
                print(f"✅ MATCH by Deep Fallback: {name_normalized} <-> {full}")
                return u

    print(f"❌ NO MATCH FOUND for Room: {room_normalized}, Name: {name_normalized}")
    return None


def get_user_info_with_parcel_count(user):
    """
    Get formatted user info with pending parcel count.
    
    Returns:
        dict with user info and parcel_count
    """
    if not user:
        return {
            "exists": False,
            "room_number": "",
            "first_name": "",
            "last_name": "",
            "display_name": "",
            "parcel_count": 0
        }
    
    room_num = user.get('room_number')
    # Calculate pending parcels for this room
    p_count = parcels_col.count_documents({"room_number": room_num, "status": "pending"})
    
    return {
        "exists": True,
        "room_number": room_num,
        "first_name": user.get('first_name', ''),
        "last_name": user.get('last_name', ''),
        "display_name": user.get('display_name', ''),
        "parcel_count": p_count
    }
