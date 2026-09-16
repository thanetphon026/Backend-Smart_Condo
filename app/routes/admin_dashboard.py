from flask import Blueprint, jsonify
from ..utils.db import parcels_col, users_col

dashboard_bp = Blueprint('dashboard', __name__)

from ..utils.helpers import get_bkk_time, token_required, is_registration_open

@dashboard_bp.route('/api/admin/dashboard/stats', methods=['GET'])
@token_required
def get_stats():
    try:
        total_parcels = parcels_col.count_documents({})
        
        in_time_all = parcels_col.count_documents({"is_after_hours": False})
        in_time_received = parcels_col.count_documents({"is_after_hours": False, "status": "received"})
        
        outside_all = parcels_col.count_documents({"is_after_hours": True})
        outside_received = parcels_col.count_documents({"is_after_hours": True, "status": "received"})
        
        total_received = parcels_col.count_documents({"status": "received"})
        total_users = users_col.count_documents({})
        
        # System Status (Dynamic Operating Hours)
        now = get_bkk_time()
        is_open, op_hours = is_registration_open(now)
        
        return jsonify({
            "status": "success",
            "data": {
                "total_users": total_users,
                "total_parcels": total_parcels,
                "in_time_all": in_time_all,
                "in_time_received": in_time_received,
                "outside_all": outside_all,
                "outside_received": outside_received,
                "total_received": total_received,
                "system_status": {
                    "registration_open": is_open,
                    "registration_start": op_hours["registration_start"],
                    "registration_end": op_hours["registration_end"],
                    "server_time": now.isoformat()
                }
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
