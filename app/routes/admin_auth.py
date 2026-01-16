from flask import Blueprint, jsonify, request, session
from ..utils.db import admins_col, log_audit
import bcrypt
import datetime
import uuid

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
            
            # Log audit
            log_audit("Admin Login", f"Admin:{admin.get('username')}", target="System", details="Login success")
            
            return jsonify({
                "status": "success", 
                "message": "Login successful",
                "session_token": session_token,
                "admin": {
                    "name": admin.get('username'),
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
    auth_header = request.headers.get('X-Admin-Name', 'Unknown')
    log_audit("Admin Logout", auth_header, target="System", details="Logout")
    return jsonify({"status": "success"})
