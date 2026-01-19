"""
Web Chat API - Mirror of LINE Webhook functionality for Web Chat interface.
Supports all LINE features except push notifications.
"""
from flask import Blueprint, request, jsonify
from ..utils.db import users_col, parcels_col, log_audit, save_chat_history
from ..utils.ai import (
    generate_chat_response, analyze_parcel_label, 
    check_match, extract_intent_and_selection, extract_selection_ids
)
from ..utils.line import (
    create_block_card, create_premium_parcel_list, create_pickup_complete_card,
    create_status_card, create_verification_result_card,
    create_cancellation_confirmation_card, create_registration_confirmation_card,
    create_registration_required_card, create_user_registration_success_card,
    create_image_error_card
)
from ..utils.cloudinary_utils import upload_image
from ..utils.helpers import get_bkk_time, token_required
import datetime
import io
import base64
import time
import re

web_chat_bp = Blueprint('web_chat', __name__, url_prefix='/api/web')


@web_chat_bp.route("/user-status", methods=['GET'])
@token_required
def get_user_status():
    """Check if user is registered in the system."""
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400
    
    user = users_col.find_one({"line_user_id": user_id})
    if user and user.get('room_number'):
        return jsonify({
            "is_registered": True,
            "user_info": {
                "room_number": user.get('room_number'),
                "first_name": user.get('first_name'),
                "last_name": user.get('last_name')
            }
        })
    return jsonify({"is_registered": False, "user_info": None})


@web_chat_bp.route("/chat", methods=['POST'])
@token_required
def handle_chat():
    """
    Main Web Chat endpoint - mirrors LINE webhook functionality.
    
    Request JSON:
    {
        "user_id": "LINE_USER_ID",
        "message": "text message",
        "display_name": "User Display Name",
        "picture_url": "Profile URL",
        "image": "base64_encoded_image (optional)",
        "image_type": "jpeg/png (optional)",
        "postback_data": "action=xxx&key=value (optional)"
    }
    
    Response JSON:
    {
        "status": "success",
        "reply": "text response",
        "flex": { LINE Flex Message JSON },
        "timestamp": "ISO timestamp"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400
        
        user_id = data.get('user_id')
        message = data.get('message', '').strip()
        display_name = data.get('display_name', 'Guest')
        picture_url = data.get('picture_url')
        image_base64 = data.get('image')
        image_type = data.get('image_type', 'jpeg')
        postback_data = data.get('postback_data')
        
        if not user_id:
            return jsonify({"error": "Missing user_id"}), 400
        
        # Get or create user
        user = users_col.find_one({"line_user_id": user_id})
        if not user:
            user = {"line_user_id": user_id, "first_name": display_name, "room_number": None}
            if picture_url:
                user["picture_url"] = picture_url
        
        # Update last active
        users_col.update_one(
            {"line_user_id": user_id}, 
            {"$set": {"last_active_at": datetime.datetime.utcnow(), "display_name": display_name}},
            upsert=True
        )
        
        # Handle different message types
        if postback_data:
            return handle_postback_web(user, user_id, postback_data)
        elif image_base64:
            return handle_image_web(user, user_id, image_base64, image_type)
        elif message:
            return handle_text_web(user, user_id, message)
        else:
            return jsonify({"error": "No message, image, or postback provided"}), 400
            
    except Exception as e:
        print(f"Web Chat Error: {e}")
        return jsonify({
            "status": "error",
            "reply": "ขออภัยค่ะ ระบบขัดข้องชั่วคราว กรุณาลองใหม่อีกครั้งค่ะ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        }), 500


def handle_text_web(user, user_id, text):
    """Handle text messages - mirrors LINE text handler."""
    save_chat_history(user_id, 'user', text, platform='web')
    
    # 1. Check for USER REGISTRATION command (always allow this)
    if text.startswith('ลงทะเบียน') or text.lower().startswith('register') or text.startswith('สมัคร'):
        reg_data = parse_user_registration_web(text)
        
        if reg_data:
            room_number, first_name, last_name, phone = reg_data
            full_name = f"{first_name} {last_name}".strip()
            
            # Update user record
            users_col.update_one(
                {"line_user_id": user_id},
                {"$set": {
                    "room_number": room_number,
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": phone,
                    "registered_at": datetime.datetime.utcnow()
                }},
                upsert=True
            )
            
            # Send success card
            card = create_user_registration_success_card(room_number, full_name, phone)
            log_audit("User Registration (Web)", f"ห้อง {room_number} - {full_name}", target="New Registration", details=f"Phone: {phone}")
            return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
        else:
            # Invalid format - show how to register
            card = create_registration_required_card(user.get('display_name'))
            return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
    
    # 2. Check if user is registered (has room_number)
    if not user.get('room_number'):
        # Not registered - prompt to register
        card = create_registration_required_card(user.get('display_name'))
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
    
    # 3. Extract Intent AND Selection
    intent, embedded_selection = extract_intent_and_selection(text)
    print(f"[Web] User: {user_id} | Intent: {intent} | Selection: {embedded_selection} | Text: {text}")
    
    # Handle combined intent+selection
    if embedded_selection and intent in ['register_outside', 'cancel']:
        if intent == 'register_outside':
            return handle_pick_parcel_web(user, user_id, embedded_selection)
        elif intent == 'cancel':
            return handle_cancel_select_parcel_web(user, user_id, embedded_selection)
    
    # Context-aware handling for 'pick_parcel'
            # Check office hours (08:30 - 17:30)
            now = get_bkk_time()
            is_office_open = (
                (now.hour == 8 and now.minute >= 30) or 
                (9 <= now.hour <= 16) or 
                (now.hour == 17 and now.minute <= 30)
            )
            
            if is_office_open:
                # Within Office Hours -> assume registration
                return handle_pick_parcel_web(user, user_id, text)
            
            # Office Closed -> smart routing
            if has_after_hours:
                # No in-time parcels but has after-hours -> assume cancellation selection
                return handle_cancel_select_parcel_web(user, user_id, text)
            else:
                # No after-hours parcels, show status card about office closed
                card = create_status_card(
                    title="ไม่อยู่ในเวลาให้บริการ",
                    status_text="❌ คุณสามารถลงทะเบียนรับได้เฉพาะเวลา 08:30 - 17:30 น. เท่านั้นค่ะ\n\nพัสดุจะถูกนำไปวางที่จุดรับของเองเวลา 18:00 น. ค่ะ",
                    color="#ff9900"
                )
                return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
        
        return handle_pick_parcel_web(user, user_id, text)
    
    # Clear context for explicit intents
    if intent in ['register_outside', 'cancel', 'check_parcel']:
        users_col.update_one({"line_user_id": user_id}, {"$set": {"context_action": None}})
    
    # Handle specific intents
    if intent == 'register_outside':
        users_col.update_one({"line_user_id": user_id}, {"$set": {"context_action": "register_select"}})
        return handle_register_outside_web(user, user_id)
    
    elif intent == 'check_parcel':
        return handle_check_parcel_web(user, user_id)
    
    elif intent == 'cancel':
        return handle_cancel_outside_web(user, user_id, text)
    
    # General -> AI Chat
    response_text = generate_chat_response(text, user)
    save_chat_history(user_id, 'assistant', response_text, platform='web')
    
    return jsonify({
        "status": "success",
        "reply": response_text,
        "timestamp": datetime.datetime.utcnow().isoformat()
    })


def parse_user_registration_web(text):
    """
    Parse user registration command.
    Format: ลงทะเบียน [เลขห้อง] [ชื่อ-สกุล] [เบอร์โทร]
    Example: ลงทะเบียน 1234 สมชาย ใจดี 0812345678
    Returns: (room_number, first_name, last_name, phone) or None
    """
    # Remove "ลงทะเบียน" keyword
    text = text.strip()
    patterns = ['ลงทะเบียน', 'register', 'สมัคร']
    for p in patterns:
        text = text.replace(p, '').strip()
    
    if not text:
        return None
    
    # Try to extract: room, name(s), phone
    parts = text.split()
    
    if len(parts) < 3:
        return None
    
    # Find phone number (10-11 digits)
    phone = None
    phone_idx = -1
    for i, part in enumerate(parts):
        clean_part = re.sub(r'[^\d]', '', part)
        if len(clean_part) >= 10:
            phone = clean_part
            phone_idx = i
            break
    
    if not phone:
        return None
    
    # Room number is typically first
    room_number = parts[0]
    
    # Name is between room and phone
    if phone_idx > 1:
        name_parts = parts[1:phone_idx]
        if len(name_parts) >= 2:
            first_name = name_parts[0]
            last_name = ' '.join(name_parts[1:])
        else:
            first_name = ' '.join(name_parts)
            last_name = ''
    else:
        first_name = parts[1] if len(parts) > 1 else ''
        last_name = ''
    
    return (room_number, first_name, last_name, phone)


def handle_register_outside_web(user, user_id):
    """Handle after-hours registration request."""
    now = get_bkk_time()
    
    # Allowed ONLY 08:30 - 17:30
    is_office_open = (
        (now.hour == 8 and now.minute >= 30) or 
        (9 <= now.hour <= 16) or 
        (now.hour == 17 and now.minute <= 30)
    )
    
    if not is_office_open:
        card = create_status_card(
            title="หมดเวลาลงทะเบียน",
            status_text="⛔ ระบบเปิดรับลงทะเบียนเฉพาะช่วงเวลา 08:30 - 17:30 น. เท่านั้นค่ะ\n\nกรุณาติดต่อรับพัสดุกับเจ้าหน้าที่นิติบุคคลในเวลาทำการค่ะ",
            color="#ff3333"
        )
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
    
    room = user.get('room_number')
    if not room:
        return jsonify({
            "status": "success",
            "reply": "ไม่พบข้อมูลห้องของคุณในระบบ กรุณาติดต่อยืนยันตัวตนกับนิติบุคคล",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    # Find pending in-time parcels
    pending_in_time = list(parcels_col.find({
        "room_number": room, "status": "pending", "is_after_hours": False
    }).sort("timestamp", 1))
    
    if not pending_in_time:
        all_pending = list(parcels_col.find({"room_number": room, "status": "pending"}).sort("timestamp", 1))
        if all_pending:
            card = create_premium_parcel_list(all_pending, title="🌙 สถานะการรับนอกเวลา", header_color="#6200ee")
            return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
        else:
            return jsonify({
                "status": "success",
                "reply": "ไม่พบพัสดุรอรับสำหรับห้องของคุณครับ",
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
    
    if len(pending_in_time) == 1:
        card = create_registration_confirmation_card(pending_in_time)
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
    else:
        all_pending = list(parcels_col.find({"room_number": room, "status": "pending"}).sort("timestamp", 1))
        card = create_premium_parcel_list(all_pending, title="🌙 เลือกพัสดุที่ต้องการรับ", header_color="#6200ee")
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})


def handle_pick_parcel_web(user, user_id, text):
    """Handle parcel selection for after-hours registration."""
    room = user.get('room_number')
    if not room:
        return jsonify({
            "status": "success",
            "reply": "ไม่พบข้อมูลห้องของคุณในระบบ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    available = list(parcels_col.find({
        "room_number": room, "status": "pending", "is_after_hours": False
    }).sort("timestamp", 1))
    
    if not available:
        return jsonify({
            "status": "success",
            "reply": "ไม่มีพัสดุในเวลาที่รอการลงทะเบียนนอกเวลาค่ะ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    now = get_bkk_time()
    is_office_open = (
        (now.hour == 8 and now.minute >= 30) or 
        (9 <= now.hour <= 16) or 
        (now.hour == 17 and now.minute <= 30)
    )
    if not is_office_open:
        card = create_status_card(
            title="หมดเวลาลงทะเบียน",
            status_text="⛔ ระบบเปิดรับลงทะเบียนเฉพาะช่วงเวลา 08:30 - 17:30 น. เท่านั้นค่ะ\n\nกรุณาติดต่อรับพัสดุกับเจ้าหน้าที่นิติบุคคลในเวลาทำการค่ะ",
            color="#ff3333"
        )
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
    
    selected_pins = extract_selection_ids(text, available)
    
    if not selected_pins:
        return jsonify({
            "status": "success",
            "reply": "น้องบอตไม่แน่ใจว่าคุณเลือกชิ้นไหน กรุณาพิมพ์ลำดับ (1, 2, 3) หรือรหัส PIN 4-5 หลักค่ะ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    selected_parcels = [p for p in available if str(p.get('pin')) in selected_pins]
    
    updated_count = 0
    updated_details = []
    
    for p in selected_parcels:
        res = parcels_col.update_one(
            {"_id": p['_id'], "status": "pending", "is_after_hours": False},
            {"$set": {"is_after_hours": True, "registered_at": datetime.datetime.utcnow()}}
        )
        if res.modified_count > 0:
            updated_count += 1
            updated_details.append(f"{p.get('transport')} ({p.get('pin')})")
    
    if updated_count > 0:
        card = create_status_card(
            title="ลงทะเบียนสำเร็จ",
            status_text=f"✅ ลงทะเบียนรับนอกเวลา {updated_count} รายการสำเร็จ:\n" + "\n".join(updated_details),
            color="#06c755"
        )
        room_name = f"ห้อง {room} - {user.get('first_name', 'Guest')}"
        log_audit("Register Outside (Web)", room_name, target="Select Parcel", details=f"PINs: {', '.join(selected_pins)}")
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
    else:
        return jsonify({
            "status": "success",
            "reply": "ไม่พบพัสดุที่คุณระบุ หรือพัสดุถูกลงทะเบียนไปแล้วค่ะ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })


def handle_check_parcel_web(user, user_id):
    """Handle parcel check request."""
    room = user.get('room_number')
    if not room:
        return jsonify({
            "status": "success",
            "reply": "ไม่พบข้อมูลห้องของคุณ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    parcels = list(parcels_col.find({"room_number": room, "status": "pending"}).sort("timestamp", 1))
    
    if not parcels:
        card = create_block_card(
            title="ไม่พบพัสดุ",
            status="0 รายการ",
            details="คุณไม่มีพัสดุคงค้างในขณะนี้",
            color="#999999"
        )
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
    
    card = create_premium_parcel_list(parcels, title="📦 รายการพัสดุรอรับ", header_color="#0066ff")
    return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})


def handle_cancel_outside_web(user, user_id, user_text=""):
    """Handle after-hours cancellation request."""
    now = get_bkk_time()
    # Check office hours (08:30 - 17:30)
    is_office_open = (
        (now.hour == 8 and now.minute >= 30) or 
        (9 <= now.hour <= 16) or 
        (now.hour == 17 and now.minute <= 30)
    )
    if not is_office_open:
        card = create_status_card(
            title="ไม่อยู่ในเวลาให้บริการ",
            status_text="❌ คุณสามารถยกเลิกการลงทะเบียนได้เฉพาะช่วงเวลา 08:30 - 17:30 น. เท่านั้นค่ะ\n\nหากต้องการยกเลิกเป็นกรณีพิเศษ กรุณาติดต่อเจ้าหน้าที่ค่ะ",
            color="#ff9900"
        )
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
    
    room = user.get('room_number')
    if not room:
        return jsonify({
            "status": "success",
            "reply": "ไม่พบข้อมูลห้องของคุณ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    to_cancel = list(parcels_col.find({"room_number": room, "status": "pending", "is_after_hours": True}))
    
    if not to_cancel:
        return jsonify({
            "status": "success",
            "reply": "ไม่พบรายการที่ลงทะเบียนนอกเวลาไว้ค่ะ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    cancel_all = "ทั้งหมด" in user_text
    
    if len(to_cancel) == 1 or cancel_all:
        users_col.update_one({"line_user_id": user_id}, {"$set": {"context_action": None}})
        card = create_cancellation_confirmation_card(to_cancel)
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
    else:
        users_col.update_one({"line_user_id": user_id}, {"$set": {"context_action": "cancel_select"}})
        card = create_premium_parcel_list(to_cancel, title="⚠️ เลือกพัสดุที่ต้องการยกเลิก", header_color="#ff9900")
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})


def handle_cancel_select_parcel_web(user, user_id, text):
    """Handle parcel selection for cancellation."""
    now = get_bkk_time()
    is_office_open = (
        (now.hour == 8 and now.minute >= 30) or 
        (9 <= now.hour <= 16) or 
        (now.hour == 17 and now.minute <= 30)
    )
    if not is_office_open:
        card = create_status_card(
            title="ไม่อยู่ในเวลาให้บริการ",
            status_text="❌ คุณสามารถยกเลิกการลงทะเบียนได้เฉพาะช่วงเวลา 08:30 - 17:30 น. เท่านั้นค่ะ",
            color="#ff9900"
        )
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
    
    room = user.get('room_number')
    if not room:
        return jsonify({
            "status": "success",
            "reply": "ไม่พบข้อมูลห้องของคุณ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    available = list(parcels_col.find({
        "room_number": room, "status": "pending", "is_after_hours": True
    }).sort("timestamp", 1))
    
    if not available:
        return jsonify({
            "status": "success",
            "reply": "ไม่พบรายการที่ลงทะเบียนนอกเวลาค่ะ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    selected_pins = extract_selection_ids(text, available)
    
    if not selected_pins:
        return jsonify({
            "status": "success",
            "reply": "น้องบอตไม่แน่ใจว่าคุณเลือกชิ้นไหน กรุณาระบุลำดับหรือรหัส PIN ที่ต้องการยกเลิกค่ะ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    selected_parcels = [p for p in available if str(p.get('pin')) in selected_pins]
    
    if not selected_parcels:
        return jsonify({
            "status": "success",
            "reply": "ไม่พบพัสดุที่คุณเลือกค่ะ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    users_col.update_one({"line_user_id": user_id}, {"$set": {"context_action": None}})
    card = create_cancellation_confirmation_card(selected_parcels)
    return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})


def handle_image_web(user, user_id, image_base64, image_type):
    """Handle image upload for self-pickup verification."""
    # 1. PRIORITY: Validate Image FIRST (Before time or database checks)
    try:
        # Check image type
        ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'heic', 'heif'}
        if image_type.lower() not in ALLOWED_EXTENSIONS:
            card = create_image_error_card(
                reason="นามสกุลไฟล์ไม่ถูกต้อง",
                detail=f"ระบบไม่รองรับไฟล์ {image_type} ค่ะ"
            )
            return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})

        # Check Base64 Size Estimation (Approximate)
        # Base64 is ~1.33x larger than binary. 10MB binary ~= 13.3MB Base64.
        # We can check len(image_base64) directly to be fast.
        MAX_B64_SIZE = 14 * 1024 * 1024 # ~10.5 MB binary safety margin
        if len(image_base64) > MAX_B64_SIZE:
             card = create_image_error_card(
                reason="ไฟล์ขนาดใหญ่เกินไป",
                detail=f"รูปภาพมีขนาดเกิน 10MB ค่ะ"
            )
             return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})

        image_bytes = base64.b64decode(image_base64)
        
        # Check Actual Binary Size (10MB limit)
        if len(image_bytes) > 10 * 1024 * 1024:
            card = create_image_error_card(
                reason="ไฟล์ขนาดใหญ่เกินไป",
                detail=f"รูปภาพมีขนาด {len(image_bytes)/(1024*1024):.1f}MB ซึ่งเกิน 10MB ค่ะ"
            )
            return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "reply": f"เกิดข้อผิดพลาดในการประมวลผลรูปภาพ: {str(e)}",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

    # 2. Check Time Restrictions (Self-Pickup Scan: 18:00 - 08:30)
    now = get_bkk_time()
    # Open from 18:00 (18:00) until 08:30 (08:29)
    is_pickup_open = (now.hour >= 18 or now.hour < 8 or (now.hour == 8 and now.minute < 30))
    
    if not is_pickup_open:
        card = create_status_card(
            title="ไม่อยู่ในเวลาให้บริการ",
            status_text="❌ ระบบสแกนรับของด้วยตนเองเปิดให้บริการเวลา 18:00 น. จนถึง 08:30 น. เท่านั้นค่ะ\n\nในช่วงเวลาทำการ (08:30 - 17:30 น.) กรุณาติดต่อรับพัสดุกับนิติบุคคลโดยตรงค่ะ",
            color="#999999"
        )
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})

    # 3. Identity and Queue Check
    if not user.get('room_number'):
        return jsonify({
            "status": "success",
            "reply": "กรุณาติดต่อยืนยันตัวตนกับนิติบุคคลก่อนใช้งานฟีเจอร์นี้ครับ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    user_room = user.get('room_number')
    
    pending_outside = list(parcels_col.find({
        "room_number": user_room, "status": "pending", "is_after_hours": True
    }))
    
    if not pending_outside:
        card = create_status_card(
            title="ไม่พบคิวพัสดุนอกเวลา",
            status_text="❌ คุณยังไม่ได้ลงทะเบียนรับของนอกเวลา หรือไม่มีพัสดุรอรับที่เตรียมไว้ในจุดรับของด้วยตนเองค่ะ",
            color="#ff3333"
        )
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
    
    # AI Analyze
    label_data = analyze_parcel_label(image_bytes)
    
    if not label_data or not label_data.get('is_label'):
        reason = (label_data.get('reason_if_not') if label_data else None) or "ไม่พบข้อมูลที่ระบุว่าเป็นพัสดุ หรือรูปภาพไม่ชัดเจนค่ะ"
        card = create_status_card(
            title="ข้อมูลไม่ถูกต้อง",
            status_text=f"❌ {reason}\n\nกรุณาถ่ายรูปหน้าพัสดุให้ชัดเจน หรือติดต่อเจ้าหน้าที่ค่ะ",
            color="#ff3333"
        )
        return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
    
    # Match logic
    match_result = check_match(label_data, user)
    is_match = match_result['is_match']
    reason = match_result['reason']
    ocr = match_result['ocr_details']
    
    # Upload to Cloudinary
    image_url = upload_image(io.BytesIO(image_bytes))
    
    room_name = f"ห้อง {user_room} - {user.get('first_name', 'Guest')}"
    log_status = "Success" if is_match else "Failed"
    log_audit(
        action=f"Self Pickup Scan (Web) ({log_status})",
        performed_by=room_name,
        target=f"Room {ocr.get('room_number', '-')}",
        details=f"OCR Name: {ocr.get('recipient_name', '-')} | Courier: {ocr.get('transport', '-')} | Image: {image_url}"
    )
    
    timestamp = int(time.time())
    
    card = create_verification_result_card(
        is_match=is_match,
        reason=reason,
        ocr_details=ocr,
        image_url=image_url,
        confirm_action={"type": "postback", "label": "ยืนยันการรับของ", "data": f"action=confirm_self&room={user_room}&verify_img={image_url}&ts={timestamp}"} if is_match else None
    )
    
    return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})


def handle_postback_web(user, user_id, postback_data):
    """Handle postback actions from flex message buttons."""
    from urllib.parse import parse_qs
    
    parsed = {k: v[0] for k, v in parse_qs(postback_data).items()}
    action = parsed.get('action')
    
    users_col.update_one({"line_user_id": user_id}, {"$set": {"last_active_at": datetime.datetime.utcnow()}})
    
    if action == 'verify_retry':
        return jsonify({
            "status": "success",
            "reply": "ยกเลิกการสแกนเรียบร้อยแล้วค่ะ คุณสามารถเลือกทำรายการอื่นหรือถ่ายรูปใหม่อีกครั้งได้ทันทีค่ะ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    if action == 'button_disabled':
        return jsonify({
            "status": "success",
            "reply": "ปุ่มนี้ไม่สามารถใช้งานได้ในสถานการณ์นี้ค่ะ กรุณาใช้ปุ่มอื่นหรือติดต่อเจ้าหน้าที่ค่ะ",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
    
    # Check stale card
    card_ts = parsed.get('ts')
    if card_ts:
        try:
            age_seconds = time.time() - int(card_ts)
            if age_seconds > 300:  # 5 minutes
                return jsonify({
                    "status": "success",
                    "reply": "บล็อกการ์ดนี้หมดอายุแล้วค่ะ กรุณาใช้บล็อกการ์ดล่าสุดหรือส่งคำสั่งใหม่ค่ะ",
                    "timestamp": datetime.datetime.utcnow().isoformat()
                })
        except:
            pass
    
    if action == 'register_after_hours_confirm':
        room = user.get('room_number')
        pins_str = parsed.get('pins', '')
        pin_list = []
        for p in pins_str.split(','):
            if not p: continue
            pin_list.append(p)
            try: pin_list.append(int(p))
            except: pass
        
        # Idempotency check
        already_done = parcels_col.count_documents({
            "room_number": str(room), "pin": {"$in": pin_list}, "status": "pending", "is_after_hours": True
        })
        total_in_request = len([p for p in pins_str.split(',') if p])
        
        if already_done >= total_in_request and total_in_request > 0:
            return jsonify({
                "status": "success",
                "reply": "รายการนี้ได้ดำเนินการไปเป็นที่เรียบร้อยแล้วค่ะ 🙏",
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
        
        result = parcels_col.update_many(
            {"room_number": str(room), "pin": {"$in": pin_list}, "status": "pending", "is_after_hours": False},
            {"$set": {"is_after_hours": True, "registered_at": datetime.datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            card = create_status_card(
                title="ลงทะเบียนสำเร็จ",
                status_text=f"✅ ลงทะเบียนรับนอกเวลา {result.modified_count} รายการสำเร็จ\n\nพัสดุพร้อมรับที่จุดรับของนอกเวลาแล้วค่ะ",
                color="#06c755"
            )
            room_name = f"ห้อง {room} - {user.get('first_name', 'Guest')}"
            log_audit("Register Outside (Web)", room_name, target="Confirm", details=f"PINs: {pins_str}")
            return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
        else:
            return jsonify({
                "status": "success",
                "reply": "ไม่สามารถลงทะเบียนได้ กรุณาลองใหม่อีกครั้งค่ะ",
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
    
    if action == 'confirm_self':
        room = parsed.get('room')
        verify_img = parsed.get('verify_img')
        
        # Idempotency check
        still_pending = parcels_col.count_documents({
            "room_number": room, "status": "pending", "is_after_hours": True
        })
        
        if still_pending == 0:
            return jsonify({
                "status": "success",
                "reply": "รายการนี้ได้ดำเนินการไปเป็นที่เรียบร้อยแล้วค่ะ 🙏",
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
        
        result = parcels_col.update_many(
            {"room_number": room, "status": "pending", "is_after_hours": True},
            {"$set": {
                "status": "received",
                "received_at": datetime.datetime.utcnow(),
                "received_by": "self_pickup_web",
                "verification_image": verify_img
            }}
        )
        
        if result.modified_count > 0:
            last_p = list(parcels_col.find({"room_number": room, "status": "received"}).sort("received_at", -1).limit(1))[0]
            remaining = parcels_col.count_documents({"room_number": room, "status": "pending"})
            
            card = create_pickup_complete_card(
                room_number=room,
                recipient_name=last_p.get('recipient_name'),
                transport=last_p.get('transport'),
                tracking_number=last_p.get('tracking_number'),
                total_remaining=remaining,
                image_url=verify_img or last_p.get('image_url')
            )
            room_name = f"ห้อง {room} - {user.get('first_name', 'Guest')}"
            log_audit("Self Pickup Success (Web)", room_name, target="รับพัสดุเองสำเร็จ", details=f"พัสดุดำเนินการแล้ว {result.modified_count} ชิ้น")
            return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
        else:
            return jsonify({
                "status": "success",
                "reply": "เกิดข้อผิดพลาด หรือพัสดุถูกรับไปแล้วค่ะ",
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
    
    if action == 'cancel_after_hours_confirm':
        room = user.get('room_number')
        pins_str = parsed.get('pins', '')
        pin_list = []
        for p in pins_str.split(','):
            if not p: continue
            pin_list.append(p)
            try: pin_list.append(int(p))
            except: pass
        
        # Idempotency check
        still_registered = parcels_col.count_documents({
            "room_number": str(room), "pin": {"$in": pin_list}, "status": "pending", "is_after_hours": True
        })
        
        if still_registered == 0:
            return jsonify({
                "status": "success",
                "reply": "รายการนี้ได้ดำเนินการไปเป็นที่เรียบร้อยแล้วค่ะ 🙏",
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
        
        result = parcels_col.update_many(
            {"room_number": str(room), "pin": {"$in": pin_list}, "status": "pending", "is_after_hours": True},
            {"$set": {"is_after_hours": False, "registered_at": None}}
        )
        
        if result.modified_count > 0:
            card = create_status_card(
                title="ยกเลิกสำเร็จ",
                status_text=f"✅ ยกเลิกการรับนอกเวลาสำเร็จ {result.modified_count} รายการ\nพัสดุจะถูกย้ายกลับมาในระบบปกติค่ะ",
                color="#ff9900"
            )
            room_name = f"ห้อง {room} - {user.get('first_name', 'Guest')}"
            log_audit("Cancel Outside (Web)", room_name, target="ยกเลิกนัดหมาย", details=f"PINs: {pins_str}")
            return jsonify({"status": "success", "flex": card, "timestamp": datetime.datetime.utcnow().isoformat()})
        else:
            return jsonify({
                "status": "success",
                "reply": "เกิดข้อผิดพลาดในการยกเลิกรายการค่ะ",
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
    
    if action == 'register_outside_trigger':
        return handle_register_outside_web(user, user_id)

    if action == 'cancel_abort' or action == 'register_abort':
        return jsonify({
            "status": "success",
            "reply": "รับทราบค่ะ ยกเลิกรายการให้เรียบร้อยแล้วค่ะ 😊",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

    # Unknown action
    return jsonify({
        "status": "success",
        "reply": "ไม่พบ action ที่ต้องการ",
        "timestamp": datetime.datetime.utcnow().isoformat()
    })


@web_chat_bp.route("/chat-history/<user_id>", methods=['GET'])
@token_required
def get_chat_history(user_id):
    """Get chat history for polling."""
    from ..utils.db import chat_history_col
    
    history = list(chat_history_col.find(
        {"line_user_id": user_id}
    ).sort("timestamp", -1).limit(20))
    
    # Reverse to chronological order
    history.reverse()
    
    return jsonify({
        "history": [{
            "role": h.get('role'),
            "message": h.get('message'),
            "image_url": h.get('image_url'),
            "timestamp": h.get('timestamp').isoformat() if h.get('timestamp') else None,
            "platform": h.get('platform', 'line')
        } for h in history]
    })
