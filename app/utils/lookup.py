"""
User Lookup Utility
Provides functions for finding users based on parcel information with fuzzy matching.
"""

from .db import users_col, parcels_col


def normalize_room(room_str):
    """
    Normalize room number for comparison.
    Removes whitespace, common prefixes, and standardizes format.
    """
    if not room_str or room_str == "N/A":
        return None
    # Convert to string, strip all whitespace, remove common prefixes
    normalized = str(room_str).strip().replace(" ", "").replace("\t", "")
    # Remove common Thai/English prefixes
    normalized = normalized.replace("Room", "").replace("room", "").replace("ห้อง", "")
    return normalized if normalized else None


def normalize_name(name_str):
    """
    Normalize name for comparison.
    Removes titles, whitespace, and converts to lowercase.
    """
    if not name_str or name_str == "N/A":
        return None
    # Strip whitespace, remove titles, lowercase for comparison
    normalized = str(name_str).strip().replace("คุณ", "").replace("Mr.", "").replace("Ms.", "").replace("Mrs.", "")
    normalized = normalized.replace(" ", "").replace("\t", "")
    return normalized if normalized else None


def find_user_by_parcel_info(room_number=None, recipient_name=None):
    """
    Find user in database based on room number and/or recipient name.
    Uses fuzzy matching strategies:
    1. Exact room match (normalized)
    2. Partial room match
    3. Name matching (first/last/display name)
    
    Returns: 
        - User document if found
        - None if not found
    """
    room_normalized = normalize_room(room_number)
    name_normalized = normalize_name(recipient_name)
    
    print(f"🔍 Lookup - Room: '{room_number}' -> '{room_normalized}', Name: '{recipient_name}' -> '{name_normalized}'")
    
    suggested_user = None
    
    # Strategy 1: Try exact room match (normalized)
    if room_normalized:
        all_users = list(users_col.find({}))
        for u in all_users:
            db_room = normalize_room(u.get('room_number'))
            if db_room and db_room == room_normalized:
                suggested_user = u
                print(f"✅ MATCH by exact room: {db_room}")
                break
    
    # Strategy 2: Try partial room match (e.g., "101" matches "101/5")
    if not suggested_user and room_normalized:
        all_users = list(users_col.find({}))
        for u in all_users:
            db_room = normalize_room(u.get('room_number'))
            if db_room:
                # Check if one contains the other
                if (room_normalized in db_room) or (db_room in room_normalized):
                    suggested_user = u
                    print(f"✅ MATCH by partial room: {room_normalized} <-> {db_room}")
                    break
    
    # Strategy 3: Try name matching (fuzzy)
    if not suggested_user and name_normalized and len(name_normalized) > 2:
        all_users = list(users_col.find({}))
        for u in all_users:
            # Try matching against first_name, last_name, display_name
            first_name = normalize_name(u.get('first_name', ''))
            last_name = normalize_name(u.get('last_name', ''))
            display_name = normalize_name(u.get('display_name', ''))
            full_name = (first_name or '') + (last_name or '')
            
            # Check if name matches any part
            if first_name and (name_normalized in first_name or first_name in name_normalized):
                suggested_user = u
                print(f"✅ MATCH by first name: {name_normalized} <-> {first_name}")
                break
            if last_name and (name_normalized in last_name or last_name in name_normalized):
                suggested_user = u
                print(f"✅ MATCH by last name: {name_normalized} <-> {last_name}")
                break
            if display_name and (name_normalized in display_name or display_name in name_normalized):
                suggested_user = u
                print(f"✅ MATCH by display name: {name_normalized} <-> {display_name}")
                break
            if full_name and (name_normalized in full_name or full_name in name_normalized):
                suggested_user = u
                print(f"✅ MATCH by full name: {name_normalized} <-> {full_name}")
                break
    
    if not suggested_user:
        print(f"❌ NO MATCH FOUND for Room: {room_normalized}, Name: {name_normalized}")
    
    return suggested_user


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
