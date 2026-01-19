from flask import Blueprint, jsonify, request, session
from ..utils.db import admins_col, log_audit
import bcrypt
import datetime
import uuid
from urllib.parse import unquote

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/api/admin/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({"status": "error", "message": "Missing email or password"}), 400

        admin = admins_col.find_one({"email": email})
        
        # NOTE: For first run if no admin exists, you might want a seed script.
        # But here we assume admin exists or we just fail.
        
        if not admin:
             return jsonify({"status": "error", "message": "Invalid email or password"}), 401

        # Check password with bcrypt
        # Assumes password in DB is hashed. 
        # If DB has plain text (from old system), this will fail.
        # Migration strategy: If your old system had plain text, you need to update them.
        stored_password = admin.get('password')
        
        if bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8')):
            # Generate Session Token
            session_token = str(uuid.uuid4())
            
            # Use Flask Session or return token for client-side storage?
            # User requirement implies RESTful, so token based.
            # Using simple simplistic session token strategy for now.
            
            # Correct Name Logic: 'name' seems to be the field (or 'username'?) 
            # User said: Niti A. DB likely has 'name' or 'username'. 
            # Code previously used 'username'. I will check generic get.
            admin_name = admin.get('name') or admin.get('username') or "Admin"
            
            # Get IP
            ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            
            # Log audit
            log_audit("Admin Login", admin_name, target="System", details=f"Admin logged in from IP: {ip}")
            
            return jsonify({
                "status": "success", 
                "message": "Login successful",
                "session_token": session_token,
                "admin": {
                    "name": admin_name,
                    "email": admin.get('email')
                }
            })
        else:
            log_audit("Admin Login Failed", "Unknown", target="System", details=f"Failed login for {email}")
            return jsonify({"status": "error", "message": "Invalid email or password"}), 401
            
    except Exception as e:
        print(f"Login Error: {e}")
        return jsonify({"status": "error", "message": "Internal Server Error"}), 500

@auth_bp.route('/api/admin/logout', methods=['POST'])
def logout():
    # In a real token system, we'd invalidate the token.
    # Here we just log it.
    raw_name = request.headers.get('X-Admin-Name', 'Unknown')
    auth_header = unquote(raw_name)
    log_audit("Admin Logout", auth_header, target="System", details="Admin logged out")
    return jsonify({"status": "success"})
