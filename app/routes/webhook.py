from flask import Blueprint, request, abort, current_app
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent, PostbackEvent
from ..utils.line import line_handler, send_message, create_block_card
from ..utils.db import users_col, parcels_col, log_audit, save_chat_history, get_bkk_time
from ..utils.ai import generate_chat_response, analyze_parcel_label, check_match, analyze_intent
from ..config import Config
import datetime
import requests
import io

webhook_bp = Blueprint('webhook', __name__)

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
    text = event.message.text.strip()
    
    # 1. Get/Create User (Implicit Registration)
    user = users_col.find_one({"line_user_id": user_id})
    if not user:
        # Ask for registration first? Assuming simplistic flow: create generic user or wait for register flow.
        # But for 'Analyze Intent' to work, we need user context.
        user = {"line_user_id": user_id, "first_name": "Guest", "room_number": None}

    save_chat_history(user_id, 'user', text)
    
    # 2. Analyze Intent
    intent = analyze_intent(text)
    print(f"User: {user_id} | Intent: {intent} | Text: {text}")

    # 3. Handle Intents
    if intent == 'register_outside':
        handle_register_outside(user, user_id)
        return

    elif intent == 'check_parcel':
        # Show Parcel Status via Block Card
        handle_check_parcel(user, user_id)
        return

    elif intent == 'cancel':
        # Cancel logic?
        # send_message(user_id, text="การยกเลิกต้องทำผ่านนิติบุคคลโดยตรงครับ")
        # Or simplistic: cancel outside hours request
        handle_cancel_outside(user, user_id)
        return
    
    # 4. General -> RAG Response (Text Only)
    response_text = generate_chat_response(text, user)
    send_message(user_id, text=response_text)
    save_chat_history(user_id, 'assistant', response_text)

def handle_register_outside(user, user_id):
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
        send_message(user_id, flex_contents=card)
        return

    room = user.get('room_number')
    if not room:
         send_message(user_id, text="ไม่พบข้อมูลห้องของคุณในระบบ กรุณาติดต่อยืนยันตัวตนกับนิติบุคคล")
         return

    # Update Pending Parcels
    result = parcels_col.update_many(
        {"room_number": room, "status": "pending", "is_after_hours": False},
        {"$set": {"is_after_hours": True, "registered_at": datetime.datetime.utcnow()}}
    )
    
    if result.modified_count > 0:
        card = create_block_card(
            title="ลงทะเบียนสำเร็จ",
            status=f"✅ {result.modified_count} รายการ",
            details="เจ้าหน้าที่กำลังเตรียมพัสดุให้คุณ กรุณามารับที่จุดบริการนอกเวลา",
            confirm_action={"type": "message", "label": "รับทราบ", "text": "รับทราบ"},
            color="#06c755"
        )
        send_message(user_id, flex_contents=card)
        log_audit("Register Outside", user_id, target=f"Room {room}", details=f"Count: {result.modified_count}")
    else:
        # Check if already registered or no parcels
        total_pending = parcels_col.count_documents({"room_number": room, "status": "pending"})
        if total_pending > 0:
             # Already registered?
             send_message(user_id, text="พัสดุของคุณถูกลงทะเบียนรับนอกเวลาไปแล้วครับ")
        else:
             send_message(user_id, text="ไม่พบพัสดุรอรับสำหรับห้องของคุณครับ")

def handle_check_parcel(user, user_id):
    room = user.get('room_number')
    if not room:
        send_message(user_id, text="ไม่พบข้อมูลห้องของคุณ")
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
         send_message(user_id, flex_contents=card)
         return
         
    # Summary
    count_in_time = sum(1 for p in parcels if not p.get('is_after_hours'))
    count_outside = len(parcels) - count_in_time
    
    details_str = f"📦 ปกติ: {count_in_time} ชิ้น\n🌙 นอกเวลา: {count_outside} ชิ้น"
    
    card = create_block_card(
            title="พัสดุรอรับ",
            status=f"รวม {len(parcels)} รายการ",
            details=details_str,
            confirm_action={"type": "message", "label": "ลงทะเบียนรับนอกเวลา", "text": "ลงทะเบียนรับนอกเวลา"} if count_in_time > 0 else None,
            color="#007bff"
    )
    send_message(user_id, flex_contents=card)

def handle_cancel_outside(user, user_id):
    room = user.get('room_number')
    if not room: return
    
    # Revert to normal
    result = parcels_col.update_many(
        {"room_number": room, "status": "pending", "is_after_hours": True},
        {"$set": {"is_after_hours": False, "registered_at": None}}
    )
    
    if result.modified_count > 0:
         send_message(user_id, text=f"✅ ยกเลิกการรับนอกเวลาสำเร็จ {result.modified_count} รายการ")
         log_audit("Cancel Outside", user_id, target=f"Room {room}", details=f"Count: {result.modified_count}")
    else:
         send_message(user_id, text="ไม่พบรายการที่จะยกเลิกครับ")

@line_handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id
    
    user = users_col.find_one({"line_user_id": user_id})
    if not user or not user.get('room_number'):
        send_message(user_id, text="กรุณาติดต่อยืนยันตัวตนกับนิติบุคคลก่อนใช้งานฟีเจอร์นี้ครับ")
        return
    
    user_room = user.get('room_number')

    # 1. Download Image
    url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
    headers = {"Authorization": f"Bearer {Config.LINE_CHANNEL_ACCESS_TOKEN}"}
    r = requests.get(url, headers=headers)
    
    if r.status_code != 200:
        send_message(user_id, text="เกิดข้อผิดพลาดในการโหลดรูปภาพ")
        return
    
    image_bytes = r.content

    # 2. Check if System is Closed for Outside Pickup?
    # Actually User says: "If verify name/room match... show Confirm button... BUT if not registered outside... check pending"
    # Logic:
    # A. Check for 'Outside Hours' parcels that are PENDING.
    # B. If found, allow matching.
    # C. IF NO 'Outside Hours' parcels, user CANNOT pick up yourself? "ถ้าไม่ลงทะเบียนนอกเวลา...แจ้งเลยว่าไม่มีพัสดุ"
    
    pending_outside = list(parcels_col.find({
        "room_number": user_room,
        "status": "pending",
        "is_after_hours": True
    }))
    
    if not pending_outside:
        # Fail immediately as per requirement
        card = create_block_card(
            title="ไม่พบพัสดุนอกเวลา",
            status="❌ ไม่ได้ลงทะเบียน",
            details="คุณยังไม่ได้ลงทะเบียนรับของนอกเวลา หรือไม่มีพัสดุคงค้าง",
            color="#ff3333"
        )
        send_message(user_id, flex_contents=card)
        return

    # 3. AI Analyze
    label_data = analyze_parcel_label(image_bytes)
    
    # 4. Match Logic
    is_match, reason = check_match(label_data, user)
    
    log_audit("User Scan", user_id, target=f"Room {user_room}", details=f"Match: {is_match} ({reason})")
    
    if is_match:
        card = create_block_card(
            title="ข้อมูลถูกต้อง",
            status="✅ ยืนยันเจ้าของพัสดุ",
            details=f"พัสดุรหัสห้อง {label_data.get('room_number','-')} ชื่อ {label_data.get('name','-')}\nตรงกับข้อมูลของคุณ",
            confirm_action={"type": "postback", "label": "ยืนยันการรับของ", "data": f"action=confirm_self&room={user_room}"},
            reject_action={"type": "message", "label": "ยกเลิก / ถ่ายใหม่", "text": "ยกเลิก"},
            color="#06c755"
        )
        send_message(user_id, flex_contents=card, image_url=None) # Image URL optionally shown if we uploaded it
    else:
        card = create_block_card(
            title="ผิดกล่อง / ไม่ใช่ของคุณ",
            status="❌ ข้อมูลไม่ตรงกัน",
            details=f"เหตุผล: {reason}\nกรุณาเก็บพัสดุไว้ที่เดิม แล้วตรวจสอบเลขห้องบนกล่องอีกครั้ง",
            reject_action={"type": "message", "label": "รับทราบ / ถ่ายใหม่", "text": "รับทราบ"},
            color="#ff3333"
        )
        send_message(user_id, flex_contents=card)

@line_handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    
    import urllib.parse
    parsed = dict(urllib.parse.parse_qsl(data))
    
    if parsed.get('action') == 'confirm_self':
        room = parsed.get('room')
        
        # Double check intent/ai logic? already passed previous step.
        # Just update status.
        result = parcels_col.update_many(
            {"room_number": room, "status": "pending", "is_after_hours": True},
            {"$set": {
                "status": "received", 
                "received_at": datetime.datetime.utcnow(),
                "received_by": "self_pickup"
            }}
        )
        
        if result.modified_count > 0:
            card = create_block_card(
                title="รับพัสดุสำเร็จ",
                status="✅ เรียบร้อยแล้ว",
                details=f"คุณได้รับพัสดุจำนวน {result.modified_count} ชิ้นแล้ว",
                color="#06c755"
            )
            send_message(user_id, flex_contents=card)
            log_audit("Self Pickup Success", user_id, target=f"Room {room}", details=f"Count: {result.modified_count}")
        else:
            send_message(user_id, text="เกิดข้อผิดพลาด หรือพัสดุถูกรับไปแล้ว")
