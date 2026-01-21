import fitz  # PyMuPDF
import re
from .ai import generate_embedding
from .db import kb_col

def process_pdf_to_kb(file_path, filename):
    """
    Extracts text from PDF, chunks it, generates embeddings, 
    and saves to MongoDB with source tracking.
    """
    try:
        # 1. Clear old data from this same filename (Overwrite Strategy)
        kb_col.delete_many({"source": filename})
        print(f"🧹 Cleared old chunks for source: {filename}")

        # 2. Open PDF
        doc = fitz.open(file_path)
        all_chunks = []

        # 3. Process each page
        for page_num, page in enumerate(doc, 1):
            text = page.get_text("text")
            
            # Simple cleaning
            text = re.sub(r'\s+', ' ', text).strip()
            if not text:
                continue

            # 4. Chunking (approx 500-1000 characters per chunk)
            # For simplicity, we chunk by page, but if page is too large, we could split more.
            # Here we just use page-level chunking for the first version.
            chunks = split_text(text, max_chars=800)
            
            for i, chunk_text in enumerate(chunks):
                print(f"🔄 Processing: {filename} - Page {page_num} - Chunk {i+1}")
                
                # 5. Generate Embedding
                vector = generate_embedding(chunk_text)
                
                if vector:
                    doc_obj = {
                        "topic": f"{filename} (Page {page_num})",
                        "content": chunk_text,
                        "tags": ["pdf", filename.lower()],
                        "source": filename,
                        "page": page_num,
                        "embedding": vector,
                        "type": "pdf"
                    }
                    all_chunks.append(doc_obj)

        # 6. Bulk Insert
        if all_chunks:
            kb_col.insert_many(all_chunks)
            print(f"✅ Successfully indexed {len(all_chunks)} chunks from {filename}")
            return True, len(all_chunks)
        
        return False, 0

    except Exception as e:
        print(f"❌ PDF Processing Error: {e}")
        return False, str(e)

def split_text(text, max_chars=800):
    """Simple character-based splitter."""
    chunks = []
    for i in range(0, len(text), max_chars):
        chunks.append(text[i : i + max_chars])
    return chunks
