from flask import Blueprint, request, jsonify
from urllib.parse import unquote
import datetime
import re
from ..utils.db import settings_col, log_audit
from ..utils.helpers import token_required, get_bkk_time, get_operating_hours, is_registration_open

settings_bp = Blueprint('settings', __name__)

TIME_REGEX = re.compile(r'^(?:[01]\d|2[0-3]):[0-5]\d$')

@settings_bp.route('/api/admin/settings/operating-hours', methods=['GET'])
@token_required
def get_hours():
    """Get current operating hours for office / after-hours registration."""
    try:
        now = get_bkk_time()
        is_open, op_hours = is_registration_open(now)
        return jsonify({
            "status": "success",
            "data": {
                "registration_start": op_hours["registration_start"],
                "registration_end": op_hours["registration_end"],
                "is_registration_open": is_open,
                "server_time": now.isoformat()
            }
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@settings_bp.route('/api/admin/settings/operating-hours', methods=['PUT'])
@token_required
def update_hours():
    """Update operating hours for after-hours parcel registration."""
    try:
        data = request.json or {}
        start = data.get('registration_start', '').strip()
        end = data.get('registration_end', '').strip()

        if not start or not end:
            return jsonify({
                "status": "error", 
                "message": "กรุณาระบุเวลาเริ่มต้นและเวลาสิ้นสุด"
            }), 400

        if not TIME_REGEX.match(start) or not TIME_REGEX.match(end):
            return jsonify({
                "status": "error", 
                "message": "รูปแบบเวลาไม่ถูกต้อง (ต้องเป็นรูปแบบ HH:MM เช่น 08:30 หรือ 17:30)"
            }), 400

        # Validate start < end
        start_h, start_m = map(int, start.split(':'))
        end_h, end_m = map(int, end.split(':'))
        if (start_h * 60 + start_m) >= (end_h * 60 + end_m):
            return jsonify({
                "status": "error",
                "message": "เวลาเริ่มต้นต้องน้อยกว่าเวลาสิ้นสุด"
            }), 400

        admin_name = unquote(request.headers.get('X-Admin-Name', 'Admin'))
        now = get_bkk_time()

        settings_col.update_one(
            {"_id": "operating_hours"},
            {
                "$set": {
                    "registration_start": start,
                    "registration_end": end,
                    "updated_at": datetime.datetime.utcnow(),
                    "updated_by": admin_name
                }
            },
            upsert=True
        )

        log_audit(
            action="Update Operating Hours",
            performed_by=admin_name,
            target="System Settings",
            details=f"เปลี่ยนเวลาลงทะเบียนรับนอกเวลาเป็น {start} - {end} น."
        )

        is_open, op_hours = is_registration_open(now)

        return jsonify({
            "status": "success",
            "message": f"บันทึกเวลาทำการ {start} - {end} น. สำเร็จ",
            "data": {
                "registration_start": start,
                "registration_end": end,
                "is_registration_open": is_open,
                "server_time": now.isoformat()
            }
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
