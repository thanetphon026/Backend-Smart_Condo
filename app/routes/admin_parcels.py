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
             
        # Uploading to Cloudinary early to get URL for preview
        img_url = upload_image(file)
        
        file.seek(0)
        file_bytes = file.read() 
        ai_data = analyze_parcel_label(file_bytes) or {}
        
        # Suggested User Lookup - BULLETPROOF MATCHING
        suggested_user = None
        extracted_room = ai_data.get('room_number')
        extracted_name = ai_data.get('recipient_name')
        
        # Normalize room number for comparison
        def normalize_room(room_str):
            if not room_str or room_str == "N/A":
                return None
            # Convert to string, strip all whitespace, remove common prefixes
            normalized = str(room_str).strip().replace(" ", "").replace("\t", "")
            # Remove common Thai/English prefixes
            normalized = normalized.replace("Room", "").replace("room", "").replace("ห้อง", "")
            return normalized if normalized else None
        
        # Normalize name for comparison
        def normalize_name(name_str):
            if not name_str or name_str == "N/A":
                return None
            # Strip whitespace, remove titles, lowercase for comparison
            normalized = str(name_str).strip().replace("คุณ", "").replace("Mr.", "").replace("Ms.", "").replace("Mrs.", "")
            normalized = normalized.replace(" ", "").replace("\t", "")
            return normalized if normalized else None
        
        room_normalized = normalize_room(extracted_room)
        name_normalized = normalize_name(extracted_name)
        
        print(f"🔍 Scan Debug - Room: '{extracted_room}' -> '{room_normalized}', Name: '{extracted_name}' -> '{name_normalized}'")
        
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
        
        if suggested_user:
             ai_data['suggested_user'] = {
                 "room_number": suggested_user.get('room_number'),
                 "name": f"{suggested_user.get('first_name','')} {suggested_user.get('last_name','')}".strip() or suggested_user.get('display_name')
             }
        
        return jsonify({
            "status": "success", 
            "data": ai_data, 
            "image_url": img_url
        })
        
    except Exception as e:
        print(f"Scan Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@parcels_bp.route('/api/admin/parcels', methods=['POST'])
def create_parcel():
    """
    Step 2: Save to DB and Notify User.
    """
    try:
        data = request.json
        admin_name = request.headers.get('X-Admin-Name', 'Admin')
        
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
            "timestamp": datetime.datetime.utcnow(),
            "created_by": admin_name
        }
        
        parcels_col.insert_one(new_parcel)
        
        # Notify User
        user = users_col.find_one({"room_number": new_parcel['room_number']})
        if user:
             card = create_block_card(
                title="พัสดุมาใหม่",
                status=f"PIN: {pin}",
                details="มีพัสดุมาใหม่ กรุณาติดต่อรับได้ที่นิติบุคคล",
                image_url=new_parcel['image_url'],
                color="#007bff"
             )
             send_message(user['line_user_id'], flex_contents=card)

        log_audit("Add Parcel", admin_name, target=f"Room {new_parcel['room_number']}", details=f"PIN: {pin}")
        
        new_parcel['_id'] = str(new_parcel['_id'])
        return jsonify({"status": "success", "data": new_parcel})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
