from flask import Blueprint, request, jsonify, Response
from ..utils.db import parcels_col, users_col, log_audit
from ..utils.helpers import get_bkk_time
from ..utils.cloudinary_utils import upload_image, validate_image
from ..utils.ai import analyze_parcel_label
from ..utils.line import send_message, create_block_card
import datetime
import csv
import io
import random
import secrets

parcels_bp = Blueprint('parcels', __name__)

def generate_pin():
    return secrets.randbelow(90000) + 10000 

@parcels_bp.route('/api/admin/parcels', methods=['GET'])
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
def confirm_receive():
    data = request.json
    pin = data.get('pin')
    admin_name = request.headers.get('X-Admin-Name', 'Admin')

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
            card = create_block_card(
                title="พัสดุถูกรับแล้ว",
                status="✅ รับโดยเจ้าหน้าที่",
                details=f"พัสดุ PIN {pin} ถูกรับเรียบร้อยแล้ว",
                color="#06c755"
            )
            # send_message logic supports flex
            send_message(user['line_user_id'], flex_contents=card)
            
        log_audit("Confirm Pickup", admin_name, target=f"Parcel {pin}", details=f"Room {result.get('room_number')}")
        return jsonify({"status": "success", "message": "Parcel received"})
    
    return jsonify({"status": "error", "message": "Parcel not found or already received"}), 404

@parcels_bp.route('/api/admin/parcels/export_outside', methods=['GET'])
def export_outside():
    admin_name = request.headers.get('X-Admin-Name', 'Admin')
    
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
def scan_parcel():
    try:
        if 'image' not in request.files:
             return jsonify({"status": "error", "message": "No image uploaded"}), 400
             
        file = request.files['image']
        if not validate_image(file):
             return jsonify({"status": "error", "message": "Invalid image format/size"}), 400
             
        img_url = upload_image(file)
        
        file.seek(0)
        file_bytes = file.read() 
        ai_data = analyze_parcel_label(file_bytes) or {}
        
        pin = generate_pin()
        new_parcel = {
            "room_number": ai_data.get('room_number', 'Unknown'),
            "recipient_name": ai_data.get('name', 'Unknown'),
            "tracking_number": ai_data.get('tracking_number', ''),
            "transport": "Unknown", 
            "image_url": img_url,
            "pin": pin,
            "status": "pending",
            "is_after_hours": False,
            "timestamp": datetime.datetime.utcnow(),
            "created_by": request.headers.get('X-Admin-Name', 'Admin')
        }
        
        parcels_col.insert_one(new_parcel)
        
        admin_name = request.headers.get('X-Admin-Name', 'Admin')
        
        # Notify if User exists
        user = users_col.find_one({"room_number": new_parcel['room_number']})
        if user:
             # Block Card Notification
             card = create_block_card(
                title="พัสดุมาใหม่",
                status=f"PIN: {pin}",
                details=f"มีพัสดุใหม่มาถึงคุณ ติดต่อรับได้ที่นิติบุคคล",
                image_url=img_url,
                color="#007bff"
             )
             send_message(user['line_user_id'], flex_contents=card)

        log_audit("Add Parcel", admin_name, target=f"Room {new_parcel['room_number']}", details=f"PIN: {pin}")

        return jsonify({"status": "success", "data": ai_data, "parcel": new_parcel})
        
    except Exception as e:
        print(f"Scan Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
