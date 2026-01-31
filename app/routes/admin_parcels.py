from flask import Blueprint, request, jsonify, Response
from urllib.parse import unquote
from ..utils.db import parcels_col, users_col, log_audit
from ..utils.helpers import get_bkk_time, token_required
from ..utils.cloudinary_utils import upload_image, validate_image
from ..utils.ai import analyze_parcel_label
from ..utils.lookup import find_user_by_parcel_info, get_user_info_with_parcel_count
from ..utils.line import (
    send_message, create_block_card, 
    create_new_parcel_notification, create_pickup_complete_card
)
import datetime
import csv
import io
import random
import secrets

parcels_bp = Blueprint('parcels', __name__)

def generate_pin():
    """Generate a 5-digit PIN that is unique among all 'pending' parcels."""
    while True:
        pin = secrets.randbelow(90000) + 10000
        # Check if this PIN is already in use by a pending parcel
        if not parcels_col.find_one({"pin": pin, "status": "pending"}):
            return pin

@parcels_bp.route('/api/admin/parcels', methods=['GET'])
@token_required
def get_parcels():
    parcel_type = request.args.get('type', 'all') 
    limit = int(request.args.get('limit', 100))
    search = request.args.get('q', '')
    
    query = {"status": "pending"} # Default show pending
    
    if parcel_type == 'in_time':
        query['is_after_hours'] = False
    elif parcel_type == 'outside':
        query['is_after_hours'] = True
    elif parcel_type == 'received':
        query['status'] = 'received'
    elif parcel_type == 'all_received':
        query['status'] = 'received'
    elif parcel_type == 'received_in_time':
        query['status'] = 'received'
        query['is_after_hours'] = False
    elif parcel_type == 'received_outside':
        query['status'] = 'received'
        query['is_after_hours'] = True  
          
    if search:
        query['$or'] = [
            {'room_number': {'$regex': search, '$options': 'i'}},
            {'recipient_name': {'$regex': search, '$options': 'i'}},
            {'tracking_number': {'$regex': search, '$options': 'i'}}
        ]
        
    parcels = list(parcels_col.find(query).sort("timestamp", -1).limit(limit))
    for p in parcels:
        p['_id'] = str(p['_id'])
        
    return jsonify({"status": "success", "data": parcels})

@parcels_bp.route('/api/admin/parcels/confirm', methods=['POST'])
@token_required
def confirm_receive():
    data = request.json
    pin = data.get('pin')
    admin_name = unquote(request.headers.get('X-Admin-Name', 'Admin'))

    if not pin:
        return jsonify({"status": "error", "message": "Missing PIN"}), 400

    result = parcels_col.find_one_and_update(
        {"pin": int(pin), "status": "pending"},
        {"$set": {
            "status": "received", 
            "picked_up_at": datetime.datetime.utcnow(),
            "picked_up_by": "admin"
        }},
        return_document=True
    )
    
    if result:
        # Notify User with Block Card
        user = users_col.find_one({"room_number": result.get('room_number')})
        if user:
            # Count remaining pending
            remaining_count = parcels_col.count_documents({"room_number": result.get('room_number'), "status": "pending"})
            
            card = create_pickup_complete_card(
                room_number=result.get('room_number'),
                recipient_name=result.get('recipient_name'),
                transport=result.get('transport'),
                tracking_number=result.get('tracking_number'),
                total_remaining=remaining_count,
                image_url=result.get('image_url')
            )
            send_message(user['line_user_id'], flex_contents=card)
            
        log_audit("Pickup Parcel", admin_name, target=f"Parcel {pin}", details=f"Room {result.get('room_number')}")
        return jsonify({"status": "success", "message": "Parcel received"})
    
    return jsonify({"status": "error", "message": "Parcel not found or already received"}), 404

@parcels_bp.route('/api/admin/parcels/export_outside', methods=['GET'])
@token_required
def export_outside():
    admin_name = unquote(request.headers.get('X-Admin-Name', 'Admin'))
    
    parcels = list(parcels_col.find({"is_after_hours": True}))
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Time', 'Room', 'Recipient', 'Carrier', 'Tracking', 'Status'])
    
    for p in parcels:
        dt = p.get('timestamp')
        date_str = dt.strftime('%Y-%m-%d') if dt else '-'
        time_str = dt.strftime('%H:%M') if dt else '-'
        
        writer.writerow([
            date_str,
            time_str,
            p.get('room_number'),
            p.get('recipient_name'),
            p.get('transport'),
            p.get('tracking_number'),
            p.get('status')
        ])
    
    log_audit("Export Outside CSV", admin_name, target="System", details="Exported outside hours parcels")
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=outside_parcels.csv"}
    )

@parcels_bp.route('/api/admin/parcels/scan', methods=['POST'])
@token_required
def scan_parcel():
    """
    Step 1: Just scan and return AI analysis. DO NOT SAVE TO DB.
    """
    try:
        if 'image' not in request.files:
             return jsonify({"status": "error", "message": "No image uploaded"}), 400
             
        file = request.files['image']
        is_valid, msg = validate_image(file)
        if not is_valid:
             return jsonify({"status": "error", "message": msg}), 400
             
        # Support skip_ai for manual entry (pure upload)
        skip_ai = request.form.get('skip_ai', 'false').lower() == 'true'
        
        # Uploading to Cloudinary early to get URL
        img_url = upload_image(file)
        
        if skip_ai:
            print("🚀 Skip AI requested: Pure upload mode")
            return jsonify({
                "status": "success",
                "data": {
                    "image_url": img_url,
                    "room_number": "",
                    "recipient_name": "",
                    "transport": "",
                    "tracking_number": "",
                    "user_found": {"exists": False},
                    "parcel_count": 0
                }
            })

        file.seek(0)
        file_bytes = file.read() 
        ai_data = analyze_parcel_label(file_bytes) or {}
        
        # Use centralized lookup utility
        extracted_room = ai_data.get('room_number')
        extracted_name = ai_data.get('recipient_name')
        
        suggested_user = find_user_by_parcel_info(extracted_room, extracted_name)
        
        # Prepare AI Data for frontend
        ai_data['image_url'] = img_url
        ai_data['user_found'] = get_user_info_with_parcel_count(suggested_user)
        ai_data['parcel_count'] = ai_data['user_found'].get('parcel_count', 0)
        
        return jsonify({
            "status": "success", 
            "data": ai_data
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Scan Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@parcels_bp.route('/api/admin/parcels', methods=['POST'])
@token_required
def create_parcel():
    """
    Step 2: Save to DB and Notify User.
    """
    try:
        data = request.json
        admin_name = unquote(request.headers.get('X-Admin-Name', 'Admin'))
        
        # Get scan_method from request (default to 'ai' for backward compatibility)
        scan_method = data.get('scan_method', 'ai')  # 'ai' or 'manual'
        
        pin = generate_pin()
        new_parcel = {
            "room_number": data.get('room_number', 'Unknown'),
            "recipient_name": data.get('recipient_name', 'Unknown'),
            "tracking_number": data.get('tracking_number', ''),
            "transport": data.get('transport', 'Unknown'), 
            "image_url": data.get('image_url'),
            "pin": pin,
            "status": "pending",
            "is_after_hours": False,
            "scan_method": scan_method,  # Track import method
            "timestamp": get_bkk_time(),
            "created_by": admin_name
        }
        
        parcels_col.insert_one(new_parcel)
        
        # Notify User
        user = users_col.find_one({"room_number": new_parcel['room_number']})
        if user:
             # Count all pending for this room
             total_pending = parcels_col.count_documents({"room_number": new_parcel['room_number'], "status": "pending"})
             
             formatted_time = new_parcel['timestamp'].strftime('%d/%m/%Y %H:%M') if isinstance(new_parcel['timestamp'], datetime.datetime) else str(new_parcel['timestamp'])

             card = create_new_parcel_notification(
                room_number=new_parcel['room_number'],
                recipient_name=new_parcel['recipient_name'],
                transport=new_parcel['transport'],
                tracking_number=new_parcel['tracking_number'],
                scan_time=formatted_time,
                total_pending=total_pending,
                image_url=new_parcel['image_url']
             )
             send_message(user['line_user_id'], flex_contents=card)

        log_audit("Scan Parcel", admin_name, target=f"Room {new_parcel['room_number']}", details=f"PIN: {pin}")
        
        new_parcel['_id'] = str(new_parcel['_id'])
        if isinstance(new_parcel['timestamp'], datetime.datetime):
            new_parcel['timestamp'] = new_parcel['timestamp'].isoformat()

        return jsonify({
            "status": "success", 
            "pin": pin,
            "data": new_parcel
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
