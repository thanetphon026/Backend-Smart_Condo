from flask import Blueprint, request, abort, current_app, jsonify
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent, PostbackEvent, FollowEvent
from ..utils.line import (
    line_handler, send_message, reply_message, create_block_card, 
    create_premium_parcel_list, create_pickup_complete_card, 
    create_status_card, create_verification_result_card,
    create_cancellation_confirmation_card, create_registration_confirmation_card,
    create_welcome_card, create_registration_required_card, create_user_registration_success_card,
    create_image_error_card
)
from ..utils.cloudinary_utils import upload_image
from ..utils.db import users_col, parcels_col, log_audit, save_chat_history
from ..utils.ai import (
    generate_chat_response, analyze_parcel_label, 
    check_match, analyze_intent, extract_selection_ids,
    extract_intent_and_selection
)
from ..config import Config
import datetime
import requests
import io


webhook_bp = Blueprint('webhook', __name__)

@webhook_bp.route("/", methods=['GET'])
def health_check():
    try:
        from ..utils.db import mongo_client
        mongo_client.admin.command('ping')
        return jsonify({"status": "online", "db": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "online", "db": "disconnected", "error": str(e)}), 500

from ..utils.helpers import get_bkk_time

@webhook_bp.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# FollowEvent Handler - When user adds bot or unblocks
@line_handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    reply_token = event.reply_token
    
    # Try to get user display name from LINE profile
    display_name = None
    try:
        from linebot.v3.messaging import Configuration, ApiClient, MessagingApi
        config = Configuration(access_token=Config.LINE_CHANNEL_ACCESS_TOKEN)
        with ApiClient(config) as api_client:
            line_api = MessagingApi(api_client)
            profile = line_api.get_profile(user_id)
            display_name = profile.display_name
    except Exception as e:
        print(f"Failed to get LINE profile: {e}")
    
    # Check if user exists in database
    user = users_col.find_one({"line_user_id": user_id})
    
    if user and user.get('room_number'):
        # Returning user (was blocked, now unblocked)
        card = create_welcome_card(
            display_name=display_name,
            is_returning=True,
            user_info=user
        )
        reply_message(reply_token, flex_contents=card)
        log_audit("User Unblocked", f"ห้อง {user.get('room_number')} - {user.get('first_name', 'Guest')}", target="Follow Event")
    else:
        # New user - show registration prompt
        card = create_welcome_card(display_name=display_name, is_returning=False)
        reply_message(reply_token, flex_contents=card)
        
        # Create user record if not exists
        if not user:
            users_col.insert_one({
                "line_user_id": user_id,
                "display_name": display_name,
                "first_name": None,
                "last_name": None,
                "room_number": None,
                "phone": None,
                "created_at": datetime.datetime.utcnow()
            })
        log_audit("New User Follow", display_name or user_id, target="Follow Event")

# Helper function to parse user registration command
def parse_user_registration(text):
    """
    Parse user registration command.
    Format: ลงทะเบียน [เลขห้อง] [ชื่อ-สกุล] [เบอร์โทร]
    Example: ลงทะเบียน 1234 สมชาย ใจดี 0812345678
    Returns: (room_number, first_name, last_name, phone) or None
    """
    import re
    
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


@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    user_id = event.source.user_id
    reply_token = event.reply_token
    text = event.message.text.strip()
    
    # 1. Get/Create User
    user = users_col.find_one({"line_user_id": user_id})
    if not user:
        user = {"line_user_id": user_id, "first_name": "Guest", "room_number": None}

    save_chat_history(user_id, 'user', text)
    users_col.update_one({"line_user_id": user_id}, {"$set": {"last_active_at": datetime.datetime.utcnow()}}, upsert=True)
    
    # 2. Check for USER REGISTRATION command (always allow this)
    # Priority Fix: unexpected trigger from "ลงทะเบียนรับนอกเวลา"
    is_registration_cmd = (
        (text.startswith('ลงทะเบียน') and 'รับนอกเวลา' not in text) or 
        text.lower().startswith('register') or 
        text.startswith('สมัคร')
    )
    
    if is_registration_cmd:
        # Parse registration data
        reg_data = parse_user_registration(text)
        
        if reg_data:
            room_number, first_name, last_name, phone = reg_data
            full_name = f"{first_name} {last_name}".strip()
            
            # Check for duplicates (Security)
            existing_room = users_col.find_one({"room_number": room_number})
            existing_phone = users_col.find_one({"phone_number": phone})
            
            # Allow re-registration for SAME user, but block if taken by others
            if existing_room and existing_room['line_user_id'] != user_id:
                reply_message(reply_token, text=f"⚠️ ไม่สามารถลงทะเบียนได้\n\nห้อง {room_number} มีผู้ลงทะเบียนในระบบแล้วค่ะ หากมีข้อผิดพลาดกรุณาติดต่อนิติบุคคล")
                return
                
            if existing_phone and existing_phone['line_user_id'] != user_id:
                reply_message(reply_token, text=f"⚠️ ไม่สามารถลงทะเบียนได้\n\nเบอร์โทร {phone} มีผู้ใช้งานในระบบแล้วค่ะ")
                return

            # Update user record
            users_col.update_one(
                {"line_user_id": user_id},
                {"$set": {
                    "room_number": room_number,
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone_number": phone,
                    "registered_at": datetime.datetime.utcnow()
                }},
                upsert=True
            )
            
            # Send success card
            card = create_user_registration_success_card(room_number, full_name, phone)
            reply_message(reply_token, flex_contents=card)
            log_audit("User Registration", f"ห้อง {room_number} - {full_name}", target="New Registration", details=f"Phone: {phone}")
            return
        else:
            # Invalid format - show how to register
            card = create_registration_required_card(user.get('display_name'))
            reply_message(reply_token, flex_contents=card)
            return
    
    # 3. Check if user is registered (has room_number)
    if not user.get('room_number'):
        # Not registered - prompt to register
        card = create_registration_required_card(user.get('display_name'))
        reply_message(reply_token, flex_contents=card)
        return
    
    # 4. Extract Intent AND Selection (combined parsing)
    intent, embedded_selection = extract_intent_and_selection(text)
    print(f"User: {user_id} | Intent: {intent} | Selection: {embedded_selection} | Text: {text}")

    # 5. Handle combined intent+selection (e.g., "ขอรับนอกเวลา45632")
    if embedded_selection and intent in ['register_outside', 'cancel']:
        # User provided selection upfront, route directly to processing
        if intent == 'register_outside':
            handle_pick_parcel(user, user_id, embedded_selection, reply_token)
        elif intent == 'cancel':
            handle_cancel_select_parcel(user, user_id, embedded_selection, reply_token)
        return

    # 6. Context-aware handling for 'pick_parcel' (number inputs)
    if intent == 'pick_parcel':
        room = user.get('room_number')
        if room:
            # Check interaction context from user doc
            context = user.get('context_action') # e.g., 'cancel_select', 'register_select'
            
            # Priority 1: Explicit flow state
            if context == 'cancel_select':
                handle_cancel_select_parcel(user, user_id, text, reply_token)
                return
            
            # Check office hours (08:30 - 17:30)
            now = get_bkk_time()
            is_office_open = (
                (now.hour == 8 and now.minute >= 30) or 
                (9 <= now.hour <= 16) or 
                (now.hour == 17 and now.minute <= 30)
            )
            
            if is_office_open:
                # Within Office Hours -> assume registration
                handle_pick_parcel(user, user_id, text, reply_token)
                return
            
            # Office Closed -> smart routing
            if has_after_hours:
                # No in-time parcels but has after-hours -> assume cancellation selection
                handle_cancel_select_parcel(user, user_id, text, reply_token)
                return
            else:
                # No after-hours parcels, show status card about office closed
                card = create_status_card(
                    title="ไม่อยู่ในเวลาให้บริการ",
                    status_text="❌ คุณสามารถลงทะเบียนรับได้เฉพาะเวลา 08:30 - 17:30 น. เท่านั้นค่ะ\n\nพัสดุจะถูกนำไปวางที่จุดรับของเองเวลา 18:00 น. ค่ะ",
                    color="#ff9900"
                )
                reply_message(reply_token, flex_contents=card)
                return
        
        # Fallback if no room or other issues
        handle_pick_parcel(user, user_id, text, reply_token)
        return

    # 7. Clear context when explicit new intent is detected
    if intent in ['register_outside', 'cancel', 'check_parcel']:
        users_col.update_one({"line_user_id": user_id}, {"$set": {"context_action": None}})

    # 8. Handle Specific Intents
    if intent == 'register_outside':
        users_col.update_one({"line_user_id": user_id}, {"$set": {"context_action": "register_select"}})
        handle_register_outside(user, user_id, reply_token)
        return

    elif intent == 'check_parcel':
        handle_check_parcel(user, user_id, reply_token)
        return

    elif intent == 'cancel':
        handle_cancel_outside(user, user_id, reply_token, text)
        return
    
    # 9. General -> AI Chat
    response_text = generate_chat_response(text, user)
    reply_message(reply_token, text=response_text)
    save_chat_history(user_id, 'assistant', response_text)

def handle_register_outside(user, user_id, reply_token):
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
        reply_message(reply_token, flex_contents=card)
        return

    room = user.get('room_number')
    if not room:
         reply_message(reply_token, text="ไม่พบข้อมูลห้องของคุณในระบบ กรุณาติดต่อยืนยันตัวตนกับนิติบุคคล")
         return

    # Find all currently pending (in-time only)
    pending_in_time = list(parcels_col.find({
        "room_number": room, 
        "status": "pending", 
        "is_after_hours": False
    }).sort("timestamp", 1))

    if not pending_in_time:
        all_pending = list(parcels_col.find({"room_number": room, "status": "pending"}).sort("timestamp", 1))
        if all_pending:
            card = create_premium_parcel_list(all_pending, title="🌙 สถานะการรับนอกเวลา", header_color="#6200ee")
            reply_message(reply_token, flex_contents=card)
        else:
            reply_message(reply_token, text="ไม่พบพัสดุรอรับสำหรับห้องของคุณครับ")
        return

    if len(pending_in_time) == 1:
        # Single parcel: Show confirmation card
        card = create_registration_confirmation_card(pending_in_time)
        reply_message(reply_token, flex_contents=card)
    else:
        # Multiple parcels: Show selection list
        all_pending = list(parcels_col.find({"room_number": room, "status": "pending"}).sort("timestamp", 1))
        card = create_premium_parcel_list(all_pending, title="🌙 เลือกพัสดุที่ต้องการรับ", header_color="#6200ee")
        reply_message(reply_token, flex_contents=card)

def handle_pick_parcel(user, user_id, text, reply_token):
    room = user.get('room_number')
    if not room: return

    available = list(parcels_col.find({
        "room_number": room, 
        "status": "pending", 
        "is_after_hours": False
    }).sort("timestamp", 1))

    if not available:
        reply_message(reply_token, text="ไม่มีพัสดุในเวลาที่รอการลงทะเบียนนอกเวลาค่ะ")
        return

    # Allowed ONLY 08:30 - 17:30
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
        reply_message(reply_token, flex_contents=card)
        return

    # Multi-selection support
    selected_pins = extract_selection_ids(text, available)
    
    if not selected_pins:
        reply_message(reply_token, text="น้องบอตไม่แน่ใจว่าคุณเลือกชิ้นไหน กรุณาพิมพ์ลำดับ (1, 2, 3) หรือรหัส PIN 4-5 หลักค่ะ")
        return

    # Filter based on selected PINs (robust string comparison)
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
        reply_message(reply_token, flex_contents=card)
        room_name = f"ห้อง {room} - {user.get('first_name', 'Guest')}"
        log_audit("Register Outside", room_name, target="Select Parcel", details=f"PINs: {', '.join(selected_pins)}")
    else:
        reply_message(reply_token, text="ไม่พบพัสดุที่คุณระบุ หรือพัสดุถูกลงทะเบียนไปแล้วค่ะ")

def handle_check_parcel(user, user_id, reply_token):
    room = user.get('room_number')
    if not room:
        reply_message(reply_token, text="ไม่พบข้อมูลห้องของคุณ")
        return
    
    parcels = list(parcels_col.find({"room_number": room, "status": "pending"}).sort("timestamp", 1))
    
    if not parcels:
        card = create_block_card(
            title="ไม่พบพัสดุ",
            status="0 รายการ",
            details="คุณไม่มีพัสดุคงค้างในขณะนี้",
            color="#999999"
        )
        reply_message(reply_token, flex_contents=card)
        return
         
    # Show Premium Unified List Card for Check status
    card = create_premium_parcel_list(parcels, title="📦 รายการพัสดุรอรับ", header_color="#0066ff")
    reply_message(reply_token, flex_contents=card)

def handle_cancel_outside(user, user_id, reply_token, user_text=""):
    """
    Smart cancellation handler:
    - Only allowed during office hours 08:00 - 16:30
    """
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
        reply_message(reply_token, flex_contents=card)
        return

    room = user.get('room_number')
    if not room: return
    
    to_cancel = list(parcels_col.find({"room_number": room, "status": "pending", "is_after_hours": True}))
    
    if not to_cancel:
        reply_message(reply_token, text="ไม่พบรายการที่ลงทะเบียนนอกเวลาไว้ค่ะ")
        return
    
    # Check if user said "ทั้งหมด" (all)
    cancel_all = "ทั้งหมด" in user_text or "ทั้งหมด" in user_text.lower()
    
    if len(to_cancel) == 1:
        # Single parcel: Show confirmation immediately
        users_col.update_one({"line_user_id": user_id}, {"$set": {"context_action": None}})
        card = create_cancellation_confirmation_card(to_cancel)
        reply_message(reply_token, flex_contents=card)
    elif cancel_all:
        # Explicit "cancel all": Show confirmation for all
        users_col.update_one({"line_user_id": user_id}, {"$set": {"context_action": None}})
        card = create_cancellation_confirmation_card(to_cancel)
        reply_message(reply_token, flex_contents=card)
    else:
        # Multiple parcels: Show selection list
        users_col.update_one({"line_user_id": user_id}, {"$set": {"context_action": "cancel_select"}})
        card = create_premium_parcel_list(
            to_cancel, 
            title="⚠️ เลือกพัสดุที่ต้องการยกเลิก", 
            header_color="#ff9900"
        )
        reply_message(reply_token, flex_contents=card)
        # Note: User will type selection, which triggers handle_cancel_select_parcel

def handle_cancel_select_parcel(user, user_id, text, reply_token):
    """
    Handle when user selects specific parcels to cancel from the list.
    """
    # Allowed ONLY 08:30 - 17:30
    now = get_bkk_time()
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
        reply_message(reply_token, flex_contents=card)
        return

    room = user.get('room_number')
    if not room: return
    
    available = list(parcels_col.find({
        "room_number": room,
        "status": "pending",
        "is_after_hours": True
    }).sort("timestamp", 1))
    
    if not available:
        reply_message(reply_token, text="ไม่พบรายการที่ลงทะเบียนนอกเวลาค่ะ")
        return
    
    # Use extraction to find selected PINs
    selected_pins = extract_selection_ids(text, available)
    
    if not selected_pins:
        reply_message(reply_token, text="น้องบอตไม่แน่ใจว่าคุณเลือกชิ้นไหน กรุณาระบุลำดับหรือรหัส PIN ที่ต้องการยกเลิกค่ะ")
        return
    
    # Get the selected parcels
    selected_parcels = [p for p in available if str(p.get('pin')) in selected_pins]
    
    if not selected_parcels:
        reply_message(reply_token, text="ไม่พบพัสดุที่คุณเลือกค่ะ")
        return
    
    # Clear context and show confirmation
    users_col.update_one({"line_user_id": user_id}, {"$set": {"context_action": None}})
    card = create_cancellation_confirmation_card(selected_parcels)
    reply_message(reply_token, flex_contents=card)

@line_handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    user_id = event.source.user_id
    reply_token = event.reply_token
    message_id = event.message.id
    
    # 1. PRIORITY: Download and Validate Image (STREAMING)
    url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
    headers = {"Authorization": f"Bearer {Config.LINE_CHANNEL_ACCESS_TOKEN}"}
    
    # Use stream=True to check headers first
    try:
        r = requests.get(url, headers=headers, stream=True, timeout=30)
        if r.status_code != 200:
            reply_message(reply_token, text="เกิดข้อผิดพลาดในการโหลดรูปภาพ")
            return
            
        # Check Content-Length header first
        content_length = r.headers.get('Content-Length')
        MAX_SIZE = 10 * 1024 * 1024  # 10 MB
        
        try:
            if content_length and int(content_length) > MAX_SIZE:
                 card = create_image_error_card(
                    reason="ไฟล์ขนาดใหญ่เกินไป",
                    detail=f"รูปภาพมีขนาด {int(content_length)/(1024*1024):.1f}MB ซึ่งเกิน 10MB ค่ะ"
                )
                 if not reply_message(reply_token, flex_contents=card):
                     # Fallback if Flex fails
                     reply_message(reply_token, text="ไฟล์ขนาดใหญ่เกิน 10MB ค่ะ (ไม่สามารถแสดงผลการ์ดได้)")
                 return
        except ValueError:
            pass # Ignore validation if header is weird, rely on streaming

        # Check Content-Type header
        content_type = r.headers.get('Content-Type', '')
        ext = content_type.split('/')[-1].lower() if '/' in content_type else 'jpeg'
        ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'heic', 'heif'}
        
        if ext not in ALLOWED_EXTENSIONS and 'image' in content_type:
            card = create_image_error_card(
                reason="นามสกุลไฟล์ไม่ถูกต้อง",
                detail=f"ระบบไม่รองรับไฟล์ {ext} ค่ะ"
            )
            if not reply_message(reply_token, flex_contents=card):
                 reply_message(reply_token, text=f"ระบบไม่รองรับไฟล์ {ext} ค่ะ")
            return

        # Download chunks and enforce strict limit
        image_bytes = bytearray()
        for chunk in r.iter_content(chunk_size=4096):
            image_bytes.extend(chunk)
            if len(image_bytes) > MAX_SIZE:
                card = create_image_error_card(
                    reason="ไฟล์ขนาดใหญ่เกินไป",
                    detail=f"รูปภาพมีขนาดเกิน 10MB ค่ะ"
                )
                if not reply_message(reply_token, flex_contents=card):
                     reply_message(reply_token, text="ไฟล์ขนาดใหญ่เกิน 10MB ค่ะ")
                return
                
        image_bytes = bytes(image_bytes)
        
    except requests.exceptions.Timeout:
         reply_message(reply_token, text="หมดเวลาดาวน์โหลดไฟล์ (Timeout) เนื่องจากไฟล์อาจมีขนาดใหญ่เกินไปค่ะ")
         return
    except Exception as e:
        print(f"Image Download Error: {e}")
        try:
            reply_message(reply_token, text="เกิดข้อผิดพลาดในการตรวจสอบไฟล์รูปภาพ")
        except:
            pass
        return

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
        reply_message(reply_token, flex_contents=card)
        return

    # 3. User Identity Check
    user = users_col.find_one({"line_user_id": user_id})
    if not user or not user.get('room_number'):
        reply_message(reply_token, text="กรุณาติดต่อยืนยันตัวตนกับนิติบุคคลก่อนใช้งานฟีเจอร์นี้ครับ")
        return
    
    users_col.update_one({"line_user_id": user_id}, {"$set": {"last_active_at": datetime.datetime.utcnow()}})
    user_room = user.get('room_number')

    pending_outside = list(parcels_col.find({
        "room_number": user_room,
        "status": "pending",
        "is_after_hours": True
    }))
    
    if not pending_outside:
        card = create_status_card(
            title="ไม่พบคิวพัสดุนอกเวลา",
            status_text="❌ คุณยังไม่ได้ลงทะเบียนรับของนอกเวลา หรือไม่มีพัสดุรอรับที่เตรียมไว้ในจุดรับของด้วยตนเองค่ะ",
            color="#ff3333"
        )
        reply_message(reply_token, flex_contents=card)
        return

    # Use stream=True for checking self-pickup verify image too
    try:
        url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
        headers = {"Authorization": f"Bearer {Config.LINE_CHANNEL_ACCESS_TOKEN}"}
        r = requests.get(url, headers=headers, stream=True)
        
        if r.status_code != 200:
            reply_message(reply_token, text="เกิดข้อผิดพลาดในการโหลดรูปภาพ")
            return
            
        # Check Content-Length first
        content_length = r.headers.get('Content-Length')
        MAX_SIZE = 10 * 1024 * 1024
        
        try:
            if content_length and int(content_length) > MAX_SIZE:
                 card = create_image_error_card(
                    reason="ไฟล์ขนาดใหญ่เกินไป",
                    detail=f"รูปภาพมีขนาด {int(content_length)/(1024*1024):.1f}MB ซึ่งเกิน 10MB ค่ะ"
                )
                 if not reply_message(reply_token, flex_contents=card):
                     reply_message(reply_token, text="ไฟล์ขนาดใหญ่เกิน 10MB ค่ะ (ไม่สามารถแสดงผลการ์ดได้)")
                 return
        except ValueError:
            pass
        
        # Check type
        content_type = r.headers.get('Content-Type', '')
        ext = content_type.split('/')[-1].lower() if '/' in content_type else 'jpeg'
        ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'heic', 'heif'}
        
        if ext not in ALLOWED_EXTENSIONS and 'image' in content_type:
            card = create_image_error_card(
                reason="นามสกุลไฟล์ไม่ถูกต้อง",
                detail=f"ระบบไม่รองรับไฟล์ {ext} ค่ะ"
            )
            if not reply_message(reply_token, flex_contents=card):
                reply_message(reply_token, text=f"ระบบไม่รองรับไฟล์ {ext} ค่ะ")
            return

        # Download chunks
        image_bytes = bytearray()
        for chunk in r.iter_content(chunk_size=4096):
            image_bytes.extend(chunk)
            if len(image_bytes) > MAX_SIZE:
                 card = create_image_error_card(
                    reason="ไฟล์ขนาดใหญ่เกินไป",
                    detail=f"รูปภาพมีขนาดเกิน 10MB ค่ะ"
                )
                 if not reply_message(reply_token, flex_contents=card):
                     reply_message(reply_token, text="ไฟล์ขนาดใหญ่เกิน 10MB ค่ะ")
                 return
                 
        image_bytes = bytes(image_bytes)

    except Exception as e:
         print(f"Image Download Error (Pickup): {e}")
         reply_message(reply_token, text="เกิดข้อผิดพลาดในการโหลดรูปภาพ")
         return

    # 4. Strict AI Analyze (Check if it's a label first)
    label_data = analyze_parcel_label(image_bytes)
    
    if not label_data.get('is_label'):
        reason = label_data.get('reason_if_not') or "ไม่พบข้อมูลที่ระบุว่าเป็นพัสดุ หรือรูปภาพไม่ชัดเจนค่ะ"
        card = create_status_card(
            title="ข้อมูลไม่ถูกต้อง",
            status_text=f"❌ {reason}\n\nกรุณาถ่ายรูปหน้าพัสดุให้ชัดเจน หรือติดต่อเจ้าหน้าที่ค่ะ",
            color="#ff3333"
        )
        reply_message(reply_token, flex_contents=card)
        return

    # 5. Robust Match Logic (If is_label is True)
    match_result = check_match(label_data, user)
    is_match = match_result['is_match']
    reason = match_result['reason']
    ocr = match_result['ocr_details']
    image_url = upload_image(io.BytesIO(image_bytes))

    room_name = f"ห้อง {user_room} - {user.get('first_name', 'Guest')}"
    log_status = "Success" if is_match else "Failed"
    log_audit(
        action=f"Self Pickup Scan ({log_status})", 
        performed_by=room_name, 
        target=f"Room {ocr.get('room_number','-')}", 
        details=f"OCR Name: {ocr.get('recipient_name','-')} | Courier: {ocr.get('transport','-')} | Match Score: {match_result.get('matched_fields', [])} | Image: {image_url}"
    )
    
    import time
    timestamp = int(time.time())
    
    card = create_verification_result_card(
        is_match=is_match,
        reason=reason,
        ocr_details=ocr,
        image_url=image_url,
        confirm_action={"type": "postback", "label": "ยืนยันการรับของ", "data": f"action=confirm_self&room={user_room}&verify_img={image_url}&ts={timestamp}"} if is_match else None
    )
    reply_message(reply_token, flex_contents=card)

@line_handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    reply_token = event.reply_token
    data = event.postback.data
    users_col.update_one({"line_user_id": user_id}, {"$set": {"last_active_at": datetime.datetime.utcnow()}})
    # Parse query string
    from urllib.parse import parse_qs
    parsed = {k: v[0] for k, v in parse_qs(data).items()}
    action = parsed.get('action')

    if action == 'verify_retry':
        reply_message(reply_token, text="ยกเลิกการสแกนเรียบร้อยแล้วค่ะ คุณสามารถเลือกทำรายการอื่นหรือถ่ายรูปใหม่อีกครั้งได้ทันทีค่ะ")
        return
    
    if action == 'button_disabled':
        reply_message(reply_token, text="ปุ่มนี้ไม่สามารถใช้งานได้ในสถานการณ์นี้ค่ะ กรุณาใช้ปุ่มอื่นหรือติดต่อเจ้าหน้าที่ค่ะ")
        return
    
    if action == 'register_after_hours_confirm':
        # Check if card is stale (> 5 minutes old)
        card_ts = parsed.get('ts')
        if card_ts:
            try:
                import time
                age_seconds = time.time() - int(card_ts)
                if age_seconds > 300:  # 5 minutes
                    reply_message(reply_token, text="บล็อกการ์ดนี้หมดอายุแล้วค่ะ กรุณาใช้บล็อกการ์ดล่าสุดหรือส่งคำสั่งใหม่ค่ะ")
                    return
            except:
                pass  # If timestamp parsing fails, allow action
        
        user = users_col.find_one({"line_user_id": user_id})
        if not user:
            reply_message(reply_token, text="ไม่พบข้อมูลผู้ใช้ค่ะ")
            return
            
        room = user.get('room_number')
        pins_str = parsed.get('pins', '')
        pin_list = []
        for p in pins_str.split(','):
            if not p: continue
            pin_list.append(p)
            try: pin_list.append(int(p))
            except: pass

        # Status-based Idempotency Check: See if any are already registered
        already_done = parcels_col.count_documents({
            "room_number": str(room), "pin": {"$in": pin_list}, "status": "pending", "is_after_hours": True
        })
        total_in_request = len(pins_str.split(','))
        
        if already_done >= total_in_request and total_in_request > 0:
            reply_message(reply_token, text="รายการนี้ได้ดำเนินการไปเป็นที่เรียบร้อยแล้วค่ะ 🙏")
            return

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
            reply_message(reply_token, flex_contents=card)
            room_name = f"ห้อง {room} - {user.get('first_name', 'Guest')}"
            log_audit("Register Outside", room_name, target="Confirm", details=f"PINs: {pins_str}")
        else:
            reply_message(reply_token, text="ไม่สามารถลงทะเบียนได้ กรุณาลองใหม่อีกครั้งค่ะ")
        return

    if action == 'confirm_self':
        # Check if card is stale (> 5 minutes old)
        card_ts = parsed.get('ts')
        if card_ts:
            try:
                import time
                age_seconds = time.time() - int(card_ts)
                if age_seconds > 300:  # 5 minutes
                    reply_message(reply_token, text="บล็อกการ์ดนี้หมดอายุแล้วค่ะ กรุณาใช้บล็อกการ์ดล่าสุดหรือส่งคำสั่งใหม่ค่ะ")
                    return
            except:
                pass  # If timestamp parsing fails, allow action

        room = parsed.get('room')
        verify_img = parsed.get('verify_img')
        
        # Status-based Idempotency Check: See if any are still pending
        still_pending = parcels_col.count_documents({
            "room_number": room, "status": "pending", "is_after_hours": True
        })
        
        if still_pending == 0:
            reply_message(reply_token, text="รายการนี้ได้ดำเนินการไปเป็นที่เรียบร้อยแล้วค่ะ 🙏")
            return

        result = parcels_col.update_many(
            {"room_number": room, "status": "pending", "is_after_hours": True},
            {"$set": {
                "status": "received", 
                "received_at": datetime.datetime.utcnow(),
                "received_by": "self_pickup",
                "verification_image": verify_img
            }}
        )
        
        if result.modified_count > 0:
            user = users_col.find_one({"line_user_id": user_id})
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
            reply_message(reply_token, flex_contents=card)
            room_name = f"ห้อง {room} - {user.get('first_name', 'Guest') if user else 'Guest'}"
            log_audit("Self Pickup Success", room_name, target="รับพัสดุเองสำเร็จ", details=f"พัสดุดำเนินการแล้ว {result.modified_count} ชิ้น")
        else:
            reply_message(reply_token, text="เกิดข้อผิดพลาด หรือพัสดุถูกรับไปแล้วค่ะ")
        return

    if action == 'cancel_after_hours_confirm':
        # Check if card is stale (> 5 minutes old)
        card_ts = parsed.get('ts')
        if card_ts:
            try:
                import time
                age_seconds = time.time() - int(card_ts)
                if age_seconds > 300:  # 5 minutes
                    reply_message(reply_token, text="บล็อกการ์ดนี้หมดอายุแล้วค่ะ กรุณาใช้บล็อกการ์ดล่าสุดหรือส่งคำสั่งใหม่ค่ะ")
                    return
            except:
                pass  # If timestamp parsing fails, allow action
        
        user = users_col.find_one({"line_user_id": user_id})
        if not user:
            reply_message(reply_token, text="ไม่พบข้อมูลผู้ใช้ค่ะ")
            return
            
        room = user.get('room_number')
        pins_str = parsed.get('pins', '')
        # Support both int and str PINs for robustness
        pin_list = []
        for p in pins_str.split(','):
            if not p: continue
            pin_list.append(p)      # string version
            try: pin_list.append(int(p)) # integer version
            except: pass

        # Status-based Idempotency Check: See if any are still registered
        still_registered = parcels_col.count_documents({
            "room_number": str(room), "pin": {"$in": pin_list}, "status": "pending", "is_after_hours": True
        })
        
        if still_registered == 0:
            reply_message(reply_token, text="รายการนี้ได้ดำเนินการไปเป็นที่เรียบร้อยแล้วค่ะ 🙏")
            return

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
            reply_message(reply_token, flex_contents=card)
            room_name = f"ห้อง {room} - {user.get('first_name', 'Guest')}"
            log_audit("Cancel Outside", room_name, target="ยกเลิกนัดหมาย", details=f"PINs: {pins_str}")
        else:
            reply_message(reply_token, text="เกิดข้อผิดพลาดในการยกเลิกรายการค่ะ")
        return

    if action == 'register_outside_trigger':
        user = users_col.find_one({"line_user_id": user_id})
        if user:
            users_col.update_one({"line_user_id": user_id}, {"$set": {"context_action": "register_select"}})
            handle_register_outside(user, user_id, reply_token)
        return

    if action == 'cancel_abort' or action == 'register_abort':
        reply_message(reply_token, text="รับทราบค่ะ ยกเลิกรายการให้เรียบร้อยแล้วค่ะ 😊")
        return
