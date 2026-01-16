"""
Parcel Service Module - Smart Condo Backend
Handles all parcel CRUD operations and after-hours logic
"""
import datetime
import random
import csv
import io
import pytz
from database import parcels_col, users_col
from audit_service import log_user_action
from image_service import upload_image_to_cloudinary, delete_image_by_url

# ================= TIME UTILITIES =================

def get_bkk_now():
    """Get current time in Bangkok timezone (UTC+7)"""
    tz = pytz.timezone('Asia/Bangkok')
    return datetime.datetime.now(tz)

def is_after_hours_open():
    """
    Check if after-hours registration is currently open
    Closes at 16:30, opens at 08:00 next day
    Returns: (is_open: bool, status_message: str)
    """
    now = get_bkk_now()
    current_time = now.time()
    
    # Define time boundaries
    close_time = datetime.time(16, 30)  # 16:30
    open_time = datetime.time(8, 0)     # 08:00
    
    # Check if between 08:00 and 16:30
    if open_time <= current_time < close_time:
        return True, "🟢 ระบบเปิดรับลงทะเบียนนอกเวลา"
    else:
        return False, "🔴 ระบบปิดรับลงทะเบียนนอกเวลา (หลัง 16:30 น.)"

# ================= PIN GENERATION =================

def generate_unique_pin():
    """Generate unique 5-digit PIN for parcel"""
    while True:
        pin = ''.join([str(random.randint(0, 9)) for _ in range(5)])
        # Check if PIN already exists
        if not parcels_col.find_one({"pin": pin}):
            return pin

# ================= PARCEL CRUD OPERATIONS =================

def create_parcel(room_number, recipient_name, courier, tracking_number, image_url):
    """
    Create new parcel entry
    Returns: (success: bool, parcel_data_or_error: dict/str, pin: str)
    """
    try:
        pin = generate_unique_pin()
        
        parcel_data = {
            "room_number": str(room_number).strip(),
            "recipient_name": recipient_name.strip(),
            "transport": courier.strip(),
            "tracking_number": tracking_number.strip(),
            "image_url": image_url,
            "pin": pin,
            "status": "pending",
            "is_after_hours": False,
            "timestamp": datetime.datetime.utcnow(),
            "received_at": None,
            "user_verification_image": None
        }
        
        result = parcels_col.insert_one(parcel_data)
        parcel_data['_id'] = str(result.inserted_id)
        
        print(f"✅ Created parcel: Room {room_number}, PIN {pin}")
        return True, parcel_data, pin
        
    except Exception as e:
        print(f"❌ Create Parcel Error: {e}")
        return False, str(e), None

def get_parcels(status=None, after_hours=None, room_number=None):
    """
    Get parcels with optional filtering
    Returns: list of parcels
    """
    try:
        query = {}
        
        if status:
            query["status"] = status
        if after_hours is not None:
            query["is_after_hours"] = after_hours
        if room_number:
            room_clean = str(room_number).replace("ห้อง", "").strip()
            query["room_number"] = {"$regex": f".*{room_clean}.*"}
        
        parcels = list(parcels_col.find(query).sort("timestamp", -1))
        
        # Convert ObjectId to string
        for p in parcels:
            p['_id'] = str(p['_id'])
        
        return parcels
        
    except Exception as e:
        print(f"❌ Get Parcels Error: {e}")
        return []

def get_parcel_by_pin(pin):
    """Get single parcel by PIN"""
    try:
        parcel = parcels_col.find_one({"pin": pin})
        if parcel:
            parcel['_id'] = str(parcel['_id'])
        return parcel
    except Exception as e:
        print(f"❌ Get Parcel by PIN Error: {e}")
        return None

def update_parcel_status(pin, new_status, verification_image=None):
    """
    Update parcel status
    Args:
        pin: Parcel PIN
        new_status: 'pending' or 'received'
        verification_image: Optional user verification image URL
    Returns: bool - Success status
    """
    try:
        update_data = {
            "status": new_status
        }
        
        if new_status == "received":
            update_data["received_at"] = datetime.datetime.utcnow()
        
        if verification_image:
            update_data["user_verification_image"] = verification_image
        
        result = parcels_col.update_one(
            {"pin": pin},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            print(f"✅ Updated parcel {pin} to {new_status}")
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Update Parcel Status Error: {e}")
        return False

def register_after_hours(pins_list, line_user_id, room_number):
    """
    Register parcels for after-hours pickup
    Args:
        pins_list: List of PINs or "ALL"
        line_user_id: User's LINE ID
        room_number: User's room number
    Returns: (success: bool, count: int, message: str)
    """
    try:
        # Check if after-hours registration is open
        is_open, status_msg = is_after_hours_open()
        if not is_open:
            return False, 0, "ขออภัยค่ะ ระบบปิดรับลงทะเบียนนอกเวลาแล้ว (หลัง 16:30 น.) กรุณาลงทะเบียนก่อน 16:30 น. ในวันถัดไปค่ะ"
        
        # Get user's pending parcels
        room_clean = str(room_number).replace("ห้อง", "").strip()
        query = {
            "room_number": {"$regex": f".*{room_clean}.*"},
            "status": "pending"
        }
        
        user_parcels = list(parcels_col.find(query))
        
        if not user_parcels:
            return False, 0, "ไม่พบพัสดุสำหรับลงทะเบียนรับนอกเวลาค่ะ"
        
        # Determine which parcels to register
        if pins_list == "ALL":
            parcels_to_register = user_parcels
        else:
            parcels_to_register = [p for p in user_parcels if p['pin'] in pins_list]
        
        if not parcels_to_register:
            return False, 0, "ไม่พบพัสดุที่ต้องการลงทะเบียนค่ะ"
        
        # Update parcels to after-hours
        registered_pins = [p['pin'] for p in parcels_to_register]
        result = parcels_col.update_many(
            {"pin": {"$in": registered_pins}},
            {"$set": {"is_after_hours": True}}
        )
        
        # Log user action
        log_user_action(
            action="After-hours registration",
            line_user_id=line_user_id,
            room_number=room_number,
            target=f"{len(registered_pins)} parcels",
            result="success",
            details=f"Registered PINs: {', '.join(registered_pins)}"
        )
        
        print(f"✅ Registered {len(registered_pins)} parcels for after-hours")
        return True, len(registered_pins), "ลงทะเบียนรับของนอกเวลาสำเร็จ"
        
    except Exception as e:
        print(f"❌ Register After-hours Error: {e}")
        return False, 0, str(e)

def cancel_after_hours(pins_list, line_user_id, room_number):
    """
    Cancel after-hours registration
    Returns: (success: bool, count: int, message: str)
    """
    try:
        room_clean = str(room_number).replace("ห้อง", "").strip()
        query = {
            "room_number": {"$regex": f".*{room_clean}.*"},
            "status": "pending",
            "is_after_hours": True
        }
        
        if pins_list != "ALL":
            query["pin"] = {"$in": pins_list}
        
        # Find parcels to cancel
        parcels_to_cancel = list(parcels_col.find(query))
        
        if not parcels_to_cancel:
            return False, 0, "ไม่พบรายการที่ลงทะเบียนรับนอกเวลาค่ะ"
        
        # Update to remove after-hours flag
        cancelled_pins = [p['pin'] for p in parcels_to_cancel]
        result = parcels_col.update_many(
            {"pin": {"$in": cancelled_pins}},
            {"$set": {"is_after_hours": False}}
        )
        
        # Log user action
        log_user_action(
            action="After-hours cancellation",
            line_user_id=line_user_id,
            room_number=room_number,
            target=f"{len(cancelled_pins)} parcels",
            result="success",
            details=f"Cancelled PINs: {', '.join(cancelled_pins)}"
        )
        
        print(f"✅ Cancelled {len(cancelled_pins)} after-hours registrations")
        return True, len(cancelled_pins), "ยกเลิกการลงทะเบียนรับนอกเวลาสำเร็จ"
        
    except Exception as e:
        print(f"❌ Cancel After-hours Error: {e}")
        return False, 0, str(e)

# ================= CSV EXPORT =================

def export_after_hours_parcels_csv():
    """
    Export after-hours parcels to CSV format
    Returns: str - CSV content
    """
    try:
        parcels = list(parcels_col.find({
            "is_after_hours": True,
            "status": "pending"
        }).sort("room_number", 1))
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "หมายเลขห้อง", "ชื่อผู้รับ", "บริษัทขนส่ง", "เลขพัสดุ", "PIN", "วันที่สแกน"
        ])
        
        # Data rows
        for p in parcels:
            writer.writerow([
                p.get('room_number', '-'),
                p.get('recipient_name', '-'),
                p.get('transport', '-'),
                p.get('tracking_number', '-'),
                p.get('pin', '-'),
                p.get('timestamp', datetime.datetime.utcnow()).strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return output.getvalue()
    except Exception as e:
        print(f"❌ Export After-hours CSV Error: {e}")
        return ""

# ================= STATISTICS =================

def get_parcel_statistics():
    """
    Get parcel statistics for dashboard
    Returns: dict with counts
    """
    try:
        total = parcels_col.count_documents({})
        
        # In-hours parcels
        in_hours_pending = parcels_col.count_documents({
            "is_after_hours": False,
            "status": "pending"
        })
        
        in_hours_received = parcels_col.count_documents({
            "is_after_hours": False,
            "status": "received"
        })
        
        # After-hours parcels
        after_hours_pending = parcels_col.count_documents({
            "is_after_hours": True,
            "status": "pending"
        })
        
        after_hours_received = parcels_col.count_documents({
            "is_after_hours": True,
            "status": "received"
        })
        
        # Total received
        total_received = parcels_col.count_documents({"status": "received"})
        
        # Total users
        total_users = users_col.count_documents({})
        
        return {
            "total_parcels": total,
            "in_hours_pending": in_hours_pending,
            "in_hours_received": in_hours_received,
            "after_hours_pending": after_hours_pending,
            "after_hours_received": after_hours_received,
            "total_received": total_received,
            "total_users": total_users
        }
    except Exception as e:
        print(f"❌ Get Statistics Error: {e}")
        return {
            "total_parcels": 0,
            "in_hours_pending": 0,
            "in_hours_received": 0,
            "after_hours_pending": 0,
            "after_hours_received": 0,
            "total_received": 0,
            "total_users": 0
        }
