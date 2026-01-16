"""
Smart Condo Backend - Complete Rebuild (No Complaint System)
Flask API for parcel management with LINE/Web chat integration
"""
import os
import json
import datetime
import urllib.parse
from functools import wraps
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from concurrent.futures import ThreadPoolExecutor

# Import configurations and services
from config import (
    API_TOKEN, line_handler, line_configuration,
    validate_image
)
from database import admins_col
from audit_service import (
    log_admin_action, log_user_action,
    get_admin_logs, get_user_logs,
    export_admin_logs_csv, export_user_logs_csv
)
from image_service import upload_image_to_cloudinary, upload_image_from_url
from ai_service import (
    extract_parcel_info_from_image,
    verify_parcel_image,
    get_knowledge_context,
    generate_chat_response,
    save_chat_message,
    analyze_intent
)
from parcel_service import (
    create_parcel, get_parcels, get_parcel_by_pin,
    update_parcel_status, register_after_hours, cancel_after_hours,
    export_after_hours_parcels_csv, get_parcel_statistics,
    is_after_hours_open
)
from user_service import (
    get_or_create_user, is_registered, register_user,
    find_user_by_room_or_name, update_chat_history, get_chat_history,
    search_users
)
from line_service import send_line_message, reply_line_message,send_parcel_notification

# Import Flex templates (parc only, no complaints)
from parcel_flex_templates import (
    create_parcel_registered_flex,
    create_parcel_cancelled_flex,
    create_parcel_ask_selection_flex,
    create_number_confirmation_flex,
    create_parcel_status_flex,
    create_confirm_pickup_flex
)

# LINE SDK imports
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent, FollowEvent

# ================= FLASK APP SETUP =================
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# CORS configuration
CORS(app, origins="*", allow_headers="*")
app.config['CORS_HEADERS'] = 'Content-Type'

# Background task executor
executor = ThreadPoolExecutor(max_workers=50)

# ================= SECURITY DECORATOR =================

def require_api_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        request_token = request.headers.get('X-API-Token') or request.args.get('token')
        if not request_token or request_token != API_TOKEN:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

# ================= LOGGING MIDDLEWARE =================

@app.before_request
def log_request_info():
    if request.path.startswith('/api'):
        print(f"🔍 {request.method} {request.path}")

# ================= ADMIN AUTHENTICATION =================

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    """Admin login endpoint"""
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400
        
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        
        if not email or not password:
            return jsonify({"status": "error", "message": "กรุณากรอกอีเมลและรหัสผ่าน"}), 400
        
        admin = admins_col.find_one({"email": email})
        
        if not admin or admin.get('password') != password:
            return jsonify({"status": "error", "message": "อีเมลหรือรหัสผ่านไม่ถูกต้อง"}), 401
        
        log_admin_action(
            action="Admin Login",
            performed_by=admin.get('name', email),
            target="System",
            details=f"Logged in from IP: {request.remote_addr}"
        )
        
        return jsonify({
            "status": "success",
            "message": "ล็อกอินสำเร็จ",
            "admin": {
                "name": admin.get('name'),
                "email": admin.get('email')
            }
        })
        
    except Exception as e:
        print(f"❌ Login error: {e}")
        return jsonify({"status": "error", "message": "เกิดข้อผิดพลาดในการล็อกอิน"}), 500

@app.route('/api/admin/logout', methods=['POST'])
@require_api_token
def admin_logout():
    """Admin logout endpoint"""
    try:
        admin_name = urllib.parse.unquote(request.headers.get('X-Admin-Name', 'Unknown'))
        
        log_admin_action(
            action="Admin Logout",
            performed_by=admin_name,
            target="System",
            details="Logged out"
        )
        
        return jsonify({"status": "success", "message": "Logged out"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= DASHBOARD ENDPOINTS =================

@app.route('/api/admin/dashboard-stats', methods=['GET'])
@require_api_token
def dashboard_stats():
    """Get dashboard statistics (parcels only, no complaints)"""
    try:
        stats = get_parcel_statistics()
        return jsonify({"status": "success", "data": stats})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= PARCEL MANAGEMENT ENDPOINTS =================

@app.route('/api/admin/parcels/in-hours', methods=['GET'])
@require_api_token
def get_in_hours_parcels():
    """Get in-hours parcels"""
    try:
        parcels = get_parcels(status="pending", after_hours=False)
        return jsonify({"status": "success", "data": parcels})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/parcels/after-hours', methods=['GET'])
@require_api_token
def get_after_hours_parcels():
    """Get after-hours parcels"""
    try:
        parcels = get_parcels(status="pending", after_hours=True)
        return jsonify({"status": "success", "data": parcels})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/parcels/after-hours-status', methods=['GET'])
@require_api_token
def after_hours_status():
    """Get after-hours system status"""
    try:
        is_open, status_msg = is_after_hours_open()
        return jsonify({
            "status": "success",
            "data": {
                "is_open": is_open,
                "message": status_msg
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/parcels/confirm/<pin>', methods=['POST'])
@require_api_token
def confirm_parcel(pin):
    """Confirm parcel receipt (in-hours only)"""
    try:
        admin_name = urllib.parse.unquote(request.headers.get('X-Admin-Name', 'Unknown'))
        
        # Get parcel info
        parcel = get_parcel_by_pin(pin)
        if not parcel:
            return jsonify({"status": "error", "message": "ไม่พบพัสดุ"}), 404
        
        # Update status
        if update_parcel_status(pin, "received"):
            # Send notification to user
            user = find_user_by_room_or_name(room_number=parcel['room_number'])
            if user and user.get('line_user_id'):
                # Send pickup notification
                # Send pickup notification as Flex Message
                send_parcel_notification(
                    user['line_user_id'],
                    parcel,
                    create_confirm_pickup_flex
                )
            
            # Log action
            log_admin_action(
                action="Confirm Parcel (In-hours)",
                performed_by=admin_name,
                target=f"Room {parcel['room_number']}",
                details=f"PIN: {pin}, Tracking: {parcel.get('tracking_number')}"
            )
            
            return jsonify({"status": "success", "message": "ยืนยันการรับพัสดุสำเร็จ"})
        
        return jsonify({"status": "error", "message": "ไม่สามารถอัปเดตสถานะได้"}), 500
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/parcels/export-after-hours', methods=['POST'])
@require_api_token
def export_after_hours():
    """Export after-hours parcels to CSV"""
    try:
        admin_name = urllib.parse.unquote(request.headers.get('X-Admin-Name', 'Unknown'))
        
        csv_content = export_after_hours_parcels_csv()
        
        # Log action
        log_admin_action(
            action="Export After-hours CSV",
            performed_by=admin_name,
            target="After-hours Parcels",
            details="Exported CSV file"
        )
        
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=after_hours_parcels.csv'}
        )
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= PARCEL SCANNING ENDPOINT =================

@app.route('/api/admin/scan-parcel', methods=['POST'])
@require_api_token
def scan_parcel():
    """Scan parcel image and extract information"""
    try:
        admin_name = urllib.parse.unquote(request.headers.get('X-Admin-Name', 'Unknown'))
        
        if 'image' not in request.files:
            return jsonify({"status": "error", "message": "ไม่พบไฟล์รูปภาพ"}), 400
        
        file = request.files['image']
        
        # Validate image
        is_valid, msg = validate_image(file)
        if not is_valid:
            return jsonify({"status": "error", "message": msg}), 400
        
        # Upload to Cloudinary
        success, image_url = upload_image_to_cloudinary(file)
        if not success:
            return jsonify({"status": "error", "message": "ไม่สามารถอัปโหลดรูปภาพได้"}), 500
        
        # Extract parcel info using AI
        extracted_data = extract_parcel_info_from_image(image_url)
        
        if not extracted_data['success']:
            return jsonify({"status": "error", "message": "ไม่สามารถอ่านข้อมูลพัสดุได้"}), 500
        
        # Create parcel
        success, parcel_data, pin = create_parcel(
            room_number=extracted_data['room_number'],
            recipient_name=extracted_data['recipient_name'],
            courier=extracted_data['courier'],
            tracking_number=extracted_data['tracking_number'],
            image_url=image_url
        )
        
        if success:
            # Send LINE notification to user
            user = find_user_by_room_or_name(
                room_number=extracted_data['room_number'],
                recipient_name=extracted_data['recipient_name']
            )
            
            if user and user.get('line_user_id'):
                # Send FLEX notification
                send_parcel_notification(
                    user['line_user_id'],
                    parcel_data,
                    create_parcel_registered_flex
                )
            
            # Log action
            log_admin_action(
                action="Scan Parcel",
                performed_by=admin_name,
                target=f"Room {parcel_data['room_number']}",
                details=f"PIN: {pin}, Courier: {parcel_data['transport']}"
            )
            
            return jsonify({
                "status": "success",
                "message": "สแกนพัสดุสำเร็จ",
                "data": parcel_data
            })
        
        return jsonify({"status": "error", "message": parcel_data}), 500
        
    except Exception as e:
        print(f"❌ Scan Parcel Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= AUDIT LOGS ENDPOINTS =================

@app.route('/api/admin/audit-logs/juristic', methods=['GET'])
@require_api_token
def get_juristic_logs():
    """Get juristic (admin) activity logs (20 latest)"""
    try:
        logs = get_admin_logs(limit=20)
        return jsonify({"status": "success", "data": logs})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/audit-logs/users', methods=['GET'])
@require_api_token
def get_users_logs():
    """Get user activity logs (20 latest)"""
    try:
        logs = get_user_logs(limit=20)
        return jsonify({"status": "success", "data": logs})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/audit-logs/juristic/export', methods=['POST'])
@require_api_token
def export_juristic_logs():
    """Export juristic logs to CSV"""
    try:
        admin_name = urllib.parse.unquote(request.headers.get('X-Admin-Name', 'Unknown'))
        
        csv_content = export_admin_logs_csv()
        
        log_admin_action(
            action="Export Juristic Logs CSV",
            performed_by=admin_name,
            target="Audit Logs",
            details="Exported admin activity logs"
        )
        
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=juristic_logs.csv'}
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/audit-logs/users/export', methods=['POST'])
@require_api_token
def export_users_logs():
    """Export user logs to CSV"""
    try:
        admin_name = urllib.parse.unquote(request.headers.get('X-Admin-Name', 'Unknown'))
        
        csv_content = export_user_logs_csv()
        
        log_admin_action(
            action="Export User Logs CSV",
            performed_by=admin_name,
            target="Audit Logs",
            details="Exported user activity logs"
        )
        
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=user_logs.csv'}
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= LINE WEBHOOK =================

@app.route('/webhook', methods=['POST'])
def line_webhook():
    """LINE webhook handler"""
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        return 'Invalid signature', 400
    
    return 'OK'

# ================= LINE EVENT HANDLERS =================

@line_handler.add(FollowEvent)
def handle_follow(event):
    """Handle new follower"""
    user_id = event.source.user_id
    user = get_or_create_user(user_id, platform="line")
    
    welcome_msg = (
        f"สวัสดีค่ะ! ยินดีต้อนรับสู่ Smart Condo Bot 🏢\n\n"
        f"กรุณาลงทะเบียนเพื่อใช้งานครบครัน:\n"
        f"พิมพ์: ลงทะเบียน [เลขห้อง] [ชื่อ] [นามสกุล] [เบอร์โทร]\n\n"
        f"ตัวอย่าง:\n"
        f"ลงทะเบียน 814 สมชาย ใจดี 0812345678"
    )
    
    reply_line_message(event.reply_token, welcome_msg)

@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    try:
        user_id = event.source.user_id
        text = event.message.text.strip()
        
        # Get or create user
        user = get_or_create_user(user_id, platform="line")
        
        # Save user message
        save_chat_message(user_id, "user", text, "line")
        
        # Process message
        response_data = process_user_message(user, text, platform="line")
        
        # Helper to extract text and flex from response
        response_text = response_data.get("text", "")
        flex_content = response_data.get("flex")
        
        # Save assistant response
        save_chat_message(user_id, "assistant", response_text, "line")
        update_chat_history(user_id, "assistant", response_text, "line")
        
        # Send reply
        reply_line_message(event.reply_token, response_data)
            
    except Exception as e:
        print(f"❌ Handle Message Error: {e}")
        reply_line_message(event.reply_token, "ขออภัยค่ะ ระบบเกิดข้อผิดพลาด")

@line_handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    """Handle image messages from LINE (after-hours verification)"""
    user_id = event.source.user_id
    
    user = get_or_create_user(user_id, platform="line")
    
    if not is_registered(user):
        reply_line_message(event.reply_token, "กรุณาลงทะเบียนก่อนใช้งานค่ะ")
        return
    
    # Check time and after-hours system status
    is_open, status_msg = is_after_hours_open()
    room_number = user.get('room_number')
    
    # Case 1: During business hours (08:00-16:30) - Redirect to staff
    if is_open:
        reply_line_message(
            event.reply_token,
            "ขอบคุณสำหรับรูปภาพค่ะ 📸\n\nในช่วงเวลาทำการ (08:00-16:30 น.) นิติบุคคลจะเป็นผู้ตรวจสอบและจัดส่งพัสดุให้โดยตรงค่ะ\n\nหากต้องการรับพัสดุ กรุณาแจ้ง PIN ให้เจ้าหน้าที่เมื่อมารับของนะคะ 🙏"
        )
        return
    
    # Case 2: After hours (after 16:30) - Process self-pickup verification
    try:
        from linebot.v3.messaging import ApiClient, MessagingApiBlob
        
        # Download image from LINE
        with ApiClient(line_configuration) as api_client:
            line_blob_api = MessagingApiBlob(api_client)
            message_content = line_blob_api.get_message_content(event.message.id)
            
            # Upload to Cloudinary
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                tmp_file.write(message_content)
                tmp_file.flush()
                
                with open(tmp_file.name, 'rb') as img_file:
                    success, image_url = upload_image_to_cloudinary(img_file)
            
            # Clean up temp file
            import os
            os.unlink(tmp_file.name)
        
        if not success:
            reply_line_message(event.reply_token, "ขออภัยค่ะ ไม่สามารถประมวลผลรูปภาพได้ กรุณาลองใหม่อีกครั้งค่ะ")
            
            # Log failed attempt
            log_user_action(
                action="Self-pickup scan",
                line_user_id=user_id,
                room_number=room_number,
                target="Upload failed",
                result="failure",
                details="Image upload to Cloudinary failed"
            )
            return
        
        # Get user's after-hours parcels
        pending_parcels = get_parcels(status="pending", after_hours=True, room_number=room_number)
        
        if not pending_parcels:
            response_msg = (
                "ขออภัยค่ะ ไม่พบรายการพัสดุที่ลงทะเบียนรับนอกเวลาไว้ 📦\n\n"
                "กรุณาตรวจสอบว่า:\n"
                "1. ได้ลงทะเบียนรับนอกเวลาก่อน 16:30 น. หรือยัง\n"
                "2. มีพัสดุสำหรับห้องของคุณหรือไม่\n\n"
                "หากมีปัญหา กรุณาติดต่อนิติบุคคลค่ะ 🙏"
            )
            reply_line_message(event.reply_token, response_msg)
            
            # Log - no parcels registered
            log_user_action(
                action="Self-pickup scan",
                line_user_id=user_id,
                room_number=room_number,
                target="No parcels",
                result="failure",
                details="No after-hours parcel registrations found"
            )
            return
        
        # Verify image with AI
        verification_result = verify_parcel_image(image_url, pending_parcels)
        
        # Process verification result and create response
        response_data = process_parcel_verification(
            user=user,
            verification_result=verification_result,
            user_image_url=image_url,
            platform="line"
        )
        
        # Reply with flex card or text
        reply_line_message(event.reply_token, response_data)
        
    except Exception as e:
        print(f"❌ Image Message Error: {e}")
        reply_line_message(event.reply_token, "ขออภัยค่ะ เกิดข้อผิดพลาดในการประมวลผลรูปภาพ กรุณาลองใหม่อีกครั้งค่ะ")
        
        # Log error
        log_user_action(
            action="Self-pickup scan",
            line_user_id=user_id,
            room_number=room_number,
            target="System error",
            result="failure",
            details=f"Exception: {str(e)}"
        )


# ================= MESSAGE PROCESSING LOGIC =================

def process_user_message(user, text, platform="line"):
    """
    Process user text message
    Returns: dict {"text": str, "flex": dict|None}
    """
    uid = user['line_user_id']
    
    # Priority 1: Registration
    if text.startswith("ลงทะเบียน"):
        parts = text.split()
        if len(parts) != 5:
            return {
                "text": (
                    f"📝 กรุณาลงทะเบียนให้ถูกต้อง:\n"
                    f"พิมพ์: ลงทะเบียน [เลขห้อง] [ชื่อ] [นามสกุล] [เบอร์โทร]\n\n"
                    f"ตัวอย่าง:\n"
                    f"ลงทะเบียน 814 สมชาย ใจดี 0812345678"
                )
            }
        
        _, room, fname, lname, phone = parts
        success, msg = register_user(user, room, fname, lname, phone)
        return {"text": msg}
    
    if not is_registered(user):
        return {
            "text": (
                f"สวัสดีค่ะ! กรุณาลงทะเบียนก่อนใช้งานค่ะ\n\n"
                f"พิมพ์: ลงทะเบียน [เลขห้อง] [ชื่อ] [นามสกุล] [เบอร์โทร]\n\n"
                f"ตัวอย่าง:\n"
                f"ลงทะเบียน 814 สมชาย ใจดี 0812345678"
            )
        }
    
    # Priority 3: Parcel confirmation/rejection (from Flex actions)
    if text.startswith("ยืนยันรับพัสดุ PIN:"):
        pin = text.split("PIN:")[1].strip()
        success, msg_result = confirm_pickup_by_user(user, pin)
        
        # msg_result could be string or dict
        if isinstance(msg_result, dict):
            return msg_result
        else:
            return {"text": msg_result}
        
    if text == "ไม่รับพัสดุนี้":
        return {"text": "รับทราบค่ะ ยกเลิกการรับพัสดุรายการนี้ หากต้องการรับใหม่ให้ถ่ายรูปเข้ามาใหม่นะคะ"}
        
    if text == "ถ่ายรูปพัสดุใหม่":
        return {"text": "เชิญถ่ายรูปพัสดุใหม่ได้เลยค่ะ 📸"}

    # Priority 4: Check intent
    intent = analyze_intent(text)
    
    # Check parcel status
    if intent == "CHECK_STATUS" or "พัสดุ" in text.lower() or "parcel" in text.lower():
        room_number = user.get('room_number')
        my_parcels = get_parcels(status="pending", room_number=room_number)
        
        if my_parcels:
            # Return Flex Message
            flex_content = create_parcel_status_flex(my_parcels, room_number)
            return {
                "text": f"คุณมีพัสดุรอรับ {len(my_parcels)} รายการค่ะ",
                "flex": flex_content
            }
        else:
            # Return Flex Message (Empty)
            flex_content = create_parcel_status_flex([], room_number)
            return {
                "text": f"ขณะนี้ยังไม่มีพัสดุค้างอยู่สำหรับห้อง {room_number} ค่ะ 📦",
                "flex": flex_content
            }
    
    # General chat with AI + RAG
    try:
        context = get_knowledge_context(text, user)
        response_text = generate_chat_response(text, context)
        return {"text": response_text}
    except Exception as e:
        print(f"❌ Chat Error: {e}")
        return {"text": "ขออภัยค่ะ ขณะนี้ระบบมีปัญหา กรุณาลองใหม่อีกครั้งค่ะ"}

def confirm_pickup_by_user(user, pin):
    """
    Confirm parcel pickup by user using PIN
    """
    try:
        parcel = parcels_col.find_one({"pin": pin, "status": "pending"})
        
        if not parcel:
            return False, {"text": "❌ ไม่พบพัสดุ หรือพัสดุถูกรับไปแล้วค่ะ"}
        
        # Verify ownership
        if str(parcel.get('room_number')) != str(user.get('room_number')):
            return False, {"text": "❌ ท่านไม่มีสิทธิ์รับพัสดุของห้องอื่นค่ะ"}
            
        # Update status
        update_data = {
            "status": "picked_up",
            "picked_up_at": datetime.datetime.utcnow(),
            "picked_up_by": "user_self_service",
            "pickup_method": "after_hours_ai_verified"
        }
        
        parcels_col.update_one({"_id": parcel['_id']}, {"$set": update_data})
        
        # Log action
        log_user_action(
            action="Confirm Receipt",
            line_user_id=user['line_user_id'],
            room_number=user['room_number'],
            target=f"Parcel {parcel.get('tracking_number')}",
            result="success",
            details="User confirmed receipt via AI verification"
        )
        
        # Send confirmation card (reuse admin confirmation style but with user photo context if available)
        # For simplicity, we send a text confirmation + standard flex
        from parcel_flex_templates import create_confirm_pickup_flex
        
        flex = create_confirm_pickup_flex(
            parcel,
            parcel.get('image_url'), # Original parcel image
            is_user_action=True
        )
        
        return True, {
            "text": "ยืนยันการรับพัสดุเรียบร้อยแล้วค่ะ ขอบคุณที่ใช้บริการค่ะ 🙏",
            "flex": flex
        }
        
    except Exception as e:
        print(f"❌ Confirm Pickup Error: {e}")
        return False, {"text": "เกิดข้อผิดพลาดในการยืนยันรายการค่ะ"}

def process_parcel_verification(user, verification_result, user_image_url, platform="line"):
    """
    Process parcel verification result and create response card
    Returns: dict with 'text' and 'flex'
    """
    try:
        room_number = user.get('room_number')
        line_user_id = user['line_user_id']
        
        # Case 1: Not a parcel image
        if not verification_result['is_parcel']:
            log_user_action(
                action="Self-pickup scan",
                line_user_id=line_user_id,
                room_number=room_number,
                target="Invalid image",
                result="failure",
                details="Not a parcel image"
            )
            
            return {
                "text": "ขออภัยค่ะ ไม่พบข้อมูลพัสดุในรูปภาพ กรุณาถ่ายรูปฉลากพัสดุให้ชัดเจนค่ะ",
                "flex": None
            }
        
        # Case 2: Parcel matches user's registration
        if verification_result['matches'] and verification_result['matched_parcel']:
            matched = verification_result['matched_parcel']
            
            log_user_action(
                action="Self-pickup scan",
                line_user_id=line_user_id,
                room_number=room_number,
                target=f"PIN: {matched.get('pin')}",
                result="success",
                details=f"Correct room match, Courier: {matched.get('transport')}"
            )
            
            # Create beautiful confirmation card
            flex_card = {
                "type": "bubble",
                "hero": {
                    "type": "image",
                    "url": user_image_url,
                    "size": "full",
                    "aspectRatio": "20:13",
                    "aspectMode": "cover"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "✅ ตรวจสอบแล้ว: พัสดุของคุณ!",
                            "weight": "bold",
                            "size": "xl",
                            "color": "#1DB446"
                        },
                        {
                            "type": "separator",
                            "margin": "lg"
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": f"🏠 ห้อง: {matched.get('room_number')}",
                                    "size": "sm",
                                    "margin": "md"
                                },
                                {
                                    "type": "text",
                                    "text": f"📮 บริษัท: {matched.get('transport')}",
                                    "size": "sm",
                                    "margin": "sm"
                                },
                                {
                                    "type": "text",
                                    "text": f"🔢 เลขพัสดุ: {matched.get('tracking_number')}",
                                    "size": "sm",
                                    "margin": "sm"
                                }
                            ],
                            "margin": "lg"
                        }
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#1DB446",
                            "action": {
                                "type": "message",
                                "label": "✅ ยืนยันรับของ",
                                "text": f"ยืนยันรับพัสดุ PIN:{matched.get('pin')}"
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "message",
                                "label": "❌ ปฏิเสธ",
                                "text": "ไม่รับพัสดุนี้"
                            },
                            "margin": "sm"
                        }
                    ]
                }
            }
            
            return {
                "text": "ตรวจสอบแล้ว นี่คือพัสดุของคุณค่ะ กดยืนยันรับของได้เลยค่ะ",
                "flex": flex_card
            }
        
        # Case 3: Wrong parcel (doesn't match)
        else:
            log_user_action(
                action="Self-pickup scan",
                line_user_id=line_user_id,
                room_number=room_number,
                target="Wrong parcel",
                result="failure",
                details=f"Scanned room: {verification_result.get('extracted_room')}, User room: {room_number}"
            )
            
            # Create warning card with disabled confirm button
            flex_card = {
                "type": "bubble",
                "hero": {
                    "type": "image",
                    "url": user_image_url,
                    "size": "full",
                    "aspectRatio": "20:13",
                    "aspectMode": "cover"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "⚠️ พัสดุไม่ใช่ของคุณ",
                            "weight": "bold",
                            "size": "xl",
                            "color": "#FF9900"
                        },
                        {
                            "type": "separator",
                            "margin": "lg"
                        },
                        {
                            "type": "text",
                            "text": "กรุณาเก็บกล่องนี้ไว้ที่เดิมค่ะ\nนี่เป็นพัสดุของห้องอื่น",
                            "wrap": True,
                            "color": "#666666",
                            "size": "sm",
                            "margin": "lg"
                        }
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#CCCCCC",
                            "action": {
                                "type": "message",
                                "label": "✅ ยืนยันรับ (ปิดใช้งาน)",
                                "text": "disabled"
                            },
                            "disabled": True
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "message",
                                "label": "📷 ถ่ายรูปใหม่",
                                "text": "ถ่ายรูปพัสดุใหม่"
                            },
                            "margin": "sm"
                        }
                    ]
                }
            }
            
            return {
                "text": "ขออภัยค่ะ กล่องนี้ไม่ใช่พัสดุของคุณ กรุณาเก็บไว้ที่เดิมและถ่ายรูปกล่องที่ถูกต้องค่ะ",
                "flex": flex_card
            }
        
    except Exception as e:
        print(f"❌ Process Verification Error: {e}")
        return {
            "text": "ขออภัยค่ะ เกิดข้อผิดพลาดในการประมวลผล",
            "flex": None
        }

# ================= WEB CHAT ENDPOINT (Same as LINE) =================

@app.route('/api/chat/message', methods=['POST'])
def chat_message():
    """
    Web chat endpoint - Same functionality as LINE but no auto notifications
    Requires LIFF login for user authentication
    """
    try:
        data = request.json
        message = data.get('message')
        user_id = data.get('userId')
        
        if not message or not user_id:
            return jsonify({"status": "error", "message": "Missing parameters"}), 400
            
        # Get or create user
        user = get_or_create_user(user_id, platform="web")
        
        # Save user message
        save_chat_message(user_id, "user", message, "web")
        
        # Process message
        response_data = process_user_message(user, message, platform="web")
        
        # Save assistant response
        response_text = response_data.get('text', '')
        save_chat_message(user_id, "assistant", response_text, "web")
        update_chat_history(user_id, "assistant", response_text, "web")
        
        return jsonify({
            "status": "success",
            "response": response_data  # Returns dict {text, flex}
        })
        
    except Exception as e:
        print(f"❌ Web Chat Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= HEALTH CHECK =================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "service": "Smart Condo Backend",
        "timestamp": datetime.datetime.utcnow().isoformat()
    })

@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return jsonify({
        "message": "Smart Condo API",
        "version": "2.0.0",
        "status": "running"
    })

# ================= USER MANAGEMENT ENDPOINTS =================

@app.route('/api/admin/users/search', methods=['GET'])
@require_api_token
def search_users_endpoint():
    """Search users"""
    try:
        query = request.args.get('q', '')
        users = search_users(query)
        return jsonify({"status": "success", "data": users})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= RUN APP =================

if __name__ == '__main__':
    print("🚀 Smart Condo Backend Starting...")
    print("✅ All services initialized")
    app.run(host='0.0.0.0', port=5000, debug=False)