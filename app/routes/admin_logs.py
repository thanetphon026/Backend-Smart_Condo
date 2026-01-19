from flask import Blueprint, request, jsonify, Response
from ..utils.db import audit_logs_col, log_audit
from ..utils.helpers import token_required
import csv
import io

logs_bp = Blueprint('logs', __name__)

@logs_bp.route('/api/admin/logs', methods=['GET'])
@token_required
def get_logs():
    log_type = request.args.get('type', 'admin') # admin or user
    limit = int(request.args.get('limit', 20))
    
    query = {}
    if log_type == 'user':
        # User Actions: Self Pickup Scan (Success/Failed) + Cancel
        # Note: "Self Pickup Scan (Success)" and "Self Pickup Scan (Failed)" are the audit action names used in webhook.py
        # Also include "User Scan" if that was used previously, but user authorized "Self Pickup Scan".
        # webhook.py uses: "Self Pickup Scan (Success)", "Self Pickup Scan (Failed)" and "Self Pickup Cancel"
        query['action'] = {"$in": ["Self Pickup Scan (Success)", "Self Pickup Scan (Failed)", "Self Pickup Cancel"]}
    else:
        # Admin Actions: Login, Logout, Scan Parcel (In System), Pickup Parcel (In Time)
        # Scan Parcel (In System) -> "Scan Parcel" (from admin_parcels.py)
        # Pickup Parcel (In Time) -> "Pickup Parcel" (from admin_parcels.py)
        # Admin Login -> "Admin Login"
        # Admin Logout -> "Admin Logout"
        query['action'] = {"$in": ["Admin Login", "Admin Logout", "Scan Parcel", "Pickup Parcel"]}

    logs = list(audit_logs_col.find(query).sort("timestamp", -1).limit(limit))
    for l in logs:
        l['_id'] = str(l['_id'])
        
    return jsonify({"status": "success", "data": logs})
    
@logs_bp.route('/api/admin/logs/export', methods=['GET'])
@token_required
def export_logs():
    log_type = request.args.get('type', 'admin')
    admin_name = request.headers.get('X-Admin-Name', 'Admin')
    
    query = {}
    if log_type == 'user':
        # User Actions: Self Pickup Scan (Success/Failed) + Cancel
        query['action'] = {"$in": ["Self Pickup Scan (Success)", "Self Pickup Scan (Failed)", "Self Pickup Cancel"]}
    else:
        # Admin Actions: Login, Logout, Scan Parcel, Pickup Parcel
        query['action'] = {"$in": ["Admin Login", "Admin Logout", "Scan Parcel", "Pickup Parcel"]}
        
    logs = list(audit_logs_col.find(query).sort("timestamp", -1))
    
    output = io.StringIO()
    # Add BOM for Excel compatibility with Thai characters
    output.write('\ufeff') 
    writer = csv.writer(output)
    writer.writerow(['Date', 'Performed By', 'Action', 'Target', 'Details'])
    
    for l in logs:
        dt = l.get('timestamp')
        date_str = dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '-'
        
        writer.writerow([
            date_str,
            l.get('performed_by'),
            l.get('action'),
            l.get('target'),
            l.get('details')
        ])
        
    log_audit("Export Logs", admin_name, target="System", details=f"Exported {log_type} logs")

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={log_type}_logs.csv"}
    )
