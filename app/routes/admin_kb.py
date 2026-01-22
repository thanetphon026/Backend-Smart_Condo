from flask import Blueprint, request, jsonify
from ..utils.pdf_processor import process_pdf_to_kb
from ..utils.helpers import token_required
from ..utils.db import kb_col
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
        original_filename = file.filename
        # Use a safe name for the temporary file path, but keep original for the DB
        temp_name = secure_filename(original_filename)
        # Fallback if secure_filename makes it empty (e.g. only Thai characters)
        if not temp_name or temp_name == ".pdf":
            import time
            temp_name = f"upload_{int(time.time())}.pdf"
            
        file_path = os.path.join(UPLOAD_FOLDER, temp_name)
        
        try:
            file.save(file_path)
            
            # Process the PDF using the original filename for source tracking
            success, result = process_pdf_to_kb(file_path, original_filename)
            
            # Clean up temp file
            if os.path.exists(file_path):
                os.remove(file_path)
                
            if success:
                return jsonify({
                    "message": f"Successfully indexed {result} chunks from {original_filename}",
                    "chunks": result
                }), 200
            else:
                return jsonify({"error": f"Processing failed: {result}"}), 500
                
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    
    return jsonify({"error": "Invalid file type. Only PDF allowed."}), 400

@admin_kb_bp.route('/api/admin/documents', methods=['GET'])
@token_required
def list_documents():
    """
    List all uploaded documents (grouped by source filename).
    """
    try:
        # Aggregate to find unique sources and count chunks
        pipeline = [
            {"$group": {
                "_id": "$source",
                "chunks": {"$sum": 1},
                "last_modified": {"$max": "$_id"} # Approximate last modified using ObjectId timestamp if available, or just a placeholder
            }}
        ]
        
        documents = list(kb_col.aggregate(pipeline))
        
        # Format for frontend
        results = []
        for doc in documents:
            filename = doc['_id']
            if filename:
                results.append({
                    "filename": filename,
                    "chunks": doc['chunks'],
                    "uploaded_at": doc['last_modified'].generation_time.isoformat() if hasattr(doc['last_modified'], 'generation_time') else None
                })
        
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_kb_bp.route('/api/admin/documents/<filename>', methods=['DELETE'])
@token_required
def delete_document(filename):
    """
    Delete a document and all its chunks from the knowledge base.
    """
    try:
        # Delete from MongoDB
        result = kb_col.delete_many({"source": filename})
        
        if result.deleted_count > 0:
            return jsonify({
                "message": f"Successfully deleted {filename}",
                "deleted_chunks": result.deleted_count
            }), 200
        else:
            return jsonify({"error": "Document not found"}), 404
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
