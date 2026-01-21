from flask import Blueprint, request, jsonify
from ..utils.pdf_processor import process_pdf_to_kb
from ..utils.helpers import token_required
import os
from werkzeug.utils import secure_filename

admin_kb_bp = Blueprint('admin_kb', __name__)

UPLOAD_FOLDER = 'temp_uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@admin_kb_bp.route('/api/admin/upload-pdf', methods=['POST'])
@token_required
def upload_pdf():
    """
    Endpoint for admins to upload PDF files to the knowledge base.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and file.filename.endswith('.pdf'):
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        
        try:
            file.save(file_path)
            
            # Process the PDF
            success, result = process_pdf_to_kb(file_path, filename)
            
            # Clean up temp file
            if os.path.exists(file_path):
                os.remove(file_path)
                
            if success:
                return jsonify({
                    "message": f"Successfully indexed {result} chunks from {filename}",
                    "chunks": result
                }), 200
            else:
                return jsonify({"error": f"Processing failed: {result}"}), 500
                
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return jsonify({"error": "Invalid file type. Only PDF allowed."}), 400
