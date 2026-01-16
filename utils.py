"""
Utility Functions - Smart Condo Backend
Helper functions for data processing and formatting
"""
import re
import datetime
from typing import Optional, Dict, Any

def normalize_room_number(room_input: str) -> str:
    """
    Normalize room number to standard format
    Examples: "814", "ห้อง814", "Room 814" -> "814"
    """
    if not room_input:
        return ""
    
    # Remove common prefixes
    room = str(room_input).strip()
    room = re.sub(r'^(ห้อง|Room|room|ROOM)\s*', '', room, flags=re.IGNORECASE)
    room = room.strip()
    
    # Extract only digits
    digits = re.findall(r'\d+', room)
    if digits:
        return digits[0]
    
    return room

def validate_phone_number(phone: str) -> bool:
    """
    Validate Thai phone number format
    Accepts: 0812345678, 081-234-5678, 081 234 5678
    """
    if not phone:
        return False
    
    # Remove spaces and dashes
    clean_phone = re.sub(r'[\s\-]', '', str(phone))
    
    # Check if it's 10 digits starting with 0
    if re.match(r'^0\d{9}$', clean_phone):
        return True
    
    return False

def format_datetime_thai(dt: datetime.datetime) -> str:
    """
    Format datetime to Thai format
    Example: "16 ม.ค. 2026 23:30:45"
    """
    if not dt:
        return "-"
    
    thai_months = {
        1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.",
        5: "พ.ค.", 6: "มิ.ย.", 7: "ก.ค.", 8: "ส.ค.",
        9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค."
    }
    
    try:
        if isinstance(dt, str):
            dt = datetime.datetime.fromisoformat(dt.replace('Z', '+00:00'))
        
        day = dt.day
        month = thai_months.get(dt.month, str(dt.month))
        year = dt.year + 543  # Buddhist era
        time = dt.strftime("%H:%M:%S")
        
        return f"{day} {month} {year} {time}"
    except:
        return str(dt)

def extract_numbers_from_text(text: str) -> list:
    """
    Extract all numbers from text
    Example: "1, 2, 3" -> [1, 2, 3]
    """
    if not text:
        return []
    
    numbers = re.findall(r'\d+', str(text))
    return [int(n) for n in numbers]

def is_valid_pin(pin: str) -> bool:
    """
    Validate PIN format (5 digits)
    """
    if not pin:
        return False
    
    return bool(re.match(r'^\d{5}$', str(pin)))

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe file operations
    """
    if not filename:
        return "file"
    
    # Remove special characters
    safe_name = re.sub(r'[^\w\s\-\.]', '', filename)
    safe_name = re.sub(r'\s+', '_', safe_name)
    
    return safe_name or "file"

def truncate_text(text: str, max_length: int = 100) -> str:
    """
    Truncate text to max length with ellipsis
    """
    if not text:
        return ""
    
    text = str(text).strip()
    if len(text) <= max_length:
        return text
    
    return text[:max_length-3] + "..."

def parse_parcel_selection(user_input: str, available_parcels: list) -> list:
    """
    Parse user input for parcel selection
    Examples:
    - "1, 2, 3" -> [parcel[0], parcel[1], parcel[2]]
    - "ทั้งหมด" or "ALL" -> all parcels
    - "1-3" -> [parcel[0], parcel[1], parcel[2]]
    """
    if not user_input or not available_parcels:
        return []
    
    user_input = str(user_input).strip()
    
    # Check for "all" keywords
    if any(keyword in user_input.lower() for keyword in ['all', 'ทั้งหมด', 'ทุก', 'หมด']):
        return available_parcels
    
    selected = []
    
    # Extract numbers and ranges
    parts = re.split(r'[,\s]+', user_input)
    for part in parts:
        # Check for range (e.g., "1-3")
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                for i in range(start, end + 1):
                    if 1 <= i <= len(available_parcels):
                        selected.append(available_parcels[i - 1])
            except:
                continue
        else:
            # Single number
            try:
                idx = int(part)
                if 1 <= idx <= len(available_parcels):
                    selected.append(available_parcels[idx - 1])
            except:
                continue
    
    return selected

def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate simple similarity between two strings
    Returns: 0.0 to 1.0
    """
    if not text1 or not text2:
        return 0.0
    
    text1 = str(text1).lower().strip()
    text2 = str(text2).lower().strip()
    
    if text1 == text2:
        return 1.0
    
    # Simple character overlap
    set1 = set(text1)
    set2 = set(text2)
    
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    return intersection / union if union > 0 else 0.0

def format_thai_currency(amount: float) -> str:
    """
    Format number to Thai currency
    Example: 1234.56 -> "1,234.56 บาท"
    """
    try:
        formatted = f"{amount:,.2f}"
        return f"{formatted} บาท"
    except:
        return f"{amount} บาท"

def get_time_difference_thai(dt: datetime.datetime) -> str:
    """
    Get human-readable time difference in Thai
    Example: "5 นาทีที่แล้ว", "2 ชั่วโมงที่แล้ว"
    """
    if not dt:
        return "-"
    
    try:
        if isinstance(dt, str):
            dt = datetime.datetime.fromisoformat(dt.replace('Z', '+00:00'))
        
        now = datetime.datetime.utcnow()
        if dt.tzinfo:
            now = datetime.datetime.now(dt.tzinfo)
        
        diff = now - dt
        
        seconds = diff.total_seconds()
        
        if seconds < 60:
            return "เมื่อสักครู่"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} นาทีที่แล้ว"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} ชั่วโมงที่แล้ว"
        else:
            days = int(seconds / 86400)
            return f"{days} วันที่แล้ว"
    except:
        return str(dt)
