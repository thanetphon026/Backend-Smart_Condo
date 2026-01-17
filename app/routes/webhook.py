from flask import Blueprint, request, abort, current_app, jsonify
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent, PostbackEvent
from ..utils.line import (
    line_handler, send_message, reply_message, create_block_card, 
    create_after_hours_summary_card, create_pickup_complete_card, 
    create_status_card, create_verification_result_card
)
from ..utils.cloudinary_utils import upload_image
from ..utils.db import users_col, parcels_col, log_audit, save_chat_history
from ..utils.ai import (
    generate_chat_response, analyze_parcel_label, 
    check_match, analyze_intent, extract_selection_id
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

@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    user_id = event.source.user_id
    reply_token = event.reply_token
    text = event.message.text.strip()
    
    # 1. Get/Create User (Implicit Registration)
    user = users_col.find_one({"line_user_id": user_id})
    if not user:
        # Ask for registration first? Assuming simplistic flow: create generic user or wait for register flow.
        # But for 'Analyze Intent' to work, we need user context.
        user = {"line_user_id": user_id, "first_name": "Guest", "room_number": None}

    save_chat_history(user_id, 'user', text)
    users_col.update_one({"line_user_id": user_id}, {"$set": {"last_active_at": datetime.datetime.utcnow()}})
    
    # 2. Analyze Intent
    intent = analyze_intent(text)
    print(f"User: {user_id} | Intent: {intent} | Text: {text}")

    # 3. Handle Intents
    if intent == 'register_outside':
        handle_register_outside(user, user_id, reply_token)
        return

    elif intent == 'check_parcel':
        # Show Parcel Status via Block Card
        handle_check_parcel(user, user_id, reply_token)
        return

    elif intent == 'pick_parcel':
        handle_pick_parcel(user, user_id, text, reply_token)
        return

    elif intent == 'cancel':
        handle_cancel_outside(user, user_id, reply_token)
        return
    
    # 4. General -> RAG Response (Text Only)
    response_text = generate_chat_response(text, user)
    reply_message(reply_token, text=response_text)
    save_chat_history(user_id, 'assistant', response_text)

def handle_register_outside(user, user_id, reply_token):
    now = get_bkk_time()
    cutoff = now.replace(hour=16, minute=30, second=0, microsecond=0)
    
    if now > cutoff:
        # Late
        card = create_block_card(
            title="หมดเวลาลงทะเบียน",
            status="⛔ ระบบปิดรับ 16:30 น.",
            details="กรุณาติดต่อรับพัสดุในเวลาทำการ หรือลงทะเบียนใหม่ในวันพรุ่งนี้",
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
        # Check if they have ANYTHING pending (maybe already registered)
        all_pending = list(parcels_col.find({"room_number": room, "status": "pending"}).sort("timestamp", 1))
        if all_pending:
            # Show summary so they see what's registered
            card = create_after_hours_summary_card(all_pending)
            reply_message(reply_token, flex_contents=card)
        else:
            reply_message(reply_token, text="ไม่พบพัสดุรอรับสำหรับห้องของคุณครับ")
        return

    # If exactly 1 parcel -> Auto register
    if len(pending_in_time) == 1:
        p = pending_in_time[0]
        parcels_col.update_one(
            {"_id": p['_id']},
            {"$set": {"is_after_hours": True, "registered_at": datetime.datetime.utcnow()}}
        )
        card = create_status_card(
            title="ลงทะเบียนสำเร็จ",
            status_text=f"✅ พัสดุ {p.get('transport')} ({p.get('pin')})\nถูกย้ายลงทะเบียนรับนอกเวลาเรียบร้อยแล้วค่ะ",
            color="#06c755"
        )
        reply_message(reply_token, flex_contents=card)
        room_name = f"ห้อง {room} - {user.get('first_name', 'Guest')}"
        log_audit("Register Outside", room_name, target="Auto Move", details=f"PIN: {p.get('pin')}")
    else:
        # More than 1 -> Show list and ask to pick
        all_pending = list(parcels_col.find({"room_number": room, "status": "pending"}).sort("timestamp", 1))
        card = create_after_hours_summary_card(all_pending)
        reply_message(reply_token, flex_contents=card)

def handle_pick_parcel(user, user_id, text, reply_token):
    """
    Handle user selecting a parcel from the list.
    """
    room = user.get('room_number')
    if not room: return

    # Get only in-time pending parcels for selection
    available = list(parcels_col.find({
        "room_number": room, 
        "status": "pending", 
        "is_after_hours": False
    }).sort("timestamp", 1))

    if not available:
        reply_message(reply_token, text="ไม่มีพัสดุในเวลาที่รอการลงทะเบียนนอกเวลาค่ะ")
        return

    # Use AI to find which PIN they meant
    selected_pin = extract_selection_id(text, available)
    
    if not selected_pin:
        reply_message(reply_token, text="น้องบอตไม่แน่ใจว่าคุณเลือกชิ้นไหน กรุณาพิมพ์ลำดับ (1, 2, 3) หรือรหัส PIN 4 หลักค่ะ")
        return

    # Try to update
    parcel = parcels_col.find_one_and_update(
        {"room_number": room, "pin": int(selected_pin), "is_after_hours": False},
        {"$set": {"is_after_hours": True, "registered_at": datetime.datetime.utcnow()}},
        return_document=True
    )

    if parcel:
        card = create_status_card(
            title="ลงทะเบียนสำเร็จ",
            status_text=f"✅ พัสดุ {parcel.get('transport')} (PIN: {selected_pin})\nลงทะเบียนรับนอกเวลาเรียบร้อยแล้ว",
            color="#06c755"
        )
        reply_message(reply_token, flex_contents=card)
        room_name = f"ห้อง {room} - {user.get('first_name', 'Guest')}"
        log_audit("Register Outside", room_name, target="Select Parcel", details=f"PIN: {selected_pin}")
    else:
        reply_message(reply_token, text="ไม่พบพัสดุรหัสนี้ หรือพัสดุถูกลงทะเบียนไปแล้วค่ะ")

def handle_check_parcel(user, user_id, reply_token):
    room = user.get('room_number')
    if not room:
        reply_message(reply_token, text="ไม่พบข้อมูลห้องของคุณ")
        return
    
    # Find all pending
    parcels = list(parcels_col.find({"room_number": room, "status": "pending"}))
    
    if not parcels:
         card = create_block_card(
            title="ไม่พบพัสดุ",
            status="0 รายการ",
            details="คุณไม่มีพัสดุคงค้างในขณะนี้",
            color="#999999"
        )
         reply_message(reply_token, flex_contents=card)
         return
         
    # Summary
    count_in_time = sum(1 for p in parcels if not p.get('is_after_hours'))
    count_outside = len(parcels) - count_in_time
    
    details_str = f"📦 รอในเวลา: {count_in_time} ชิ้น\n🌙 รอนอกเวลา: {count_outside} ชิ้น"
    
    card = create_block_card(
            title="พัสดุรอรับ",
            status=f"รวม {len(parcels)} รายการ",
            details=details_str,
            confirm_action={"type": "message", "label": "ลงทะเบียนรับนอกเวลา", "text": "ลงทะเบียนรับนอกเวลา"} if count_in_time > 0 else None,
            color="#0066ff"
    )
    reply_message(reply_token, flex_contents=card)

def handle_cancel_outside(user, user_id, reply_token):
    room = user.get('room_number')
    if not room: return
    
    # Revert to normal
    result = parcels_col.update_many(
        {"room_number": room, "status": "pending", "is_after_hours": True},
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
         log_audit("Cancel Outside", room_name, target="ยกเลิกนัดหมาย", details=f"พัสดุ {result.modified_count} ชิ้น")
    else:
         reply_message(reply_token, text="ไม่พบรายการที่ลงทะเบียนนอกเวลาไว้ค่ะ")

@line_handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    user_id = event.source.user_id
    reply_token = event.reply_token
    message_id = event.message.id
    now = get_bkk_time()
    
    if 8 <= now.hour < 17:
        card = create_status_card(
            title="นิติบุคคลกำลังเปิดทำการ",
            status_text="❌ ระบบสแกนรับของด้วยตนเองเปิดให้บริการเฉพาะนอกเวลาทำการ (หลัง 17:00 น.) เท่านั้นค่ะ\n\nกรุณาติดต่อรับพัสดุกับเจ้าหน้าที่นิติบุคคลโดยตรงค่ะ",
            color="#999999"
        )
        reply_message(reply_token, flex_contents=card)
        return

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

    url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
    headers = {"Authorization": f"Bearer {Config.LINE_CHANNEL_ACCESS_TOKEN}"}
    r = requests.get(url, headers=headers)
    
    if r.status_code != 200:
        reply_message(reply_token, text="เกิดข้อผิดพลาดในการโหลดรูปภาพ")
        return
    
    image_bytes = r.content
    label_data = analyze_parcel_label(image_bytes)
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
    
    card = create_verification_result_card(
        is_match=is_match,
        reason=reason,
        ocr_details=ocr,
        image_url=image_url,
        confirm_action={"type": "postback", "label": "ยืนยันการรับของ", "data": f"action=confirm_self&room={user_room}&verify_img={image_url}"} if is_match else None
    )
    reply_message(reply_token, flex_contents=card)

@line_handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    reply_token = event.reply_token
    data = event.postback.data
    users_col.update_one({"line_user_id": user_id}, {"$set": {"last_active_at": datetime.datetime.utcnow()}})
    
    import urllib.parse
    parsed = dict(urllib.parse.parse_qsl(data))
    
    if parsed.get('action') == 'confirm_self':
        room = parsed.get('room')
        verify_img = parsed.get('verify_img')
        
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
