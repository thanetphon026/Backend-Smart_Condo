def extract_keywords(text):
    """Enhanced keyword extraction with typo correction and intent expansion."""
    try:
        # Common Thai typo corrections
        typo_map = {
            'หอวข้าว': 'หาอาหาร',
            'หอว': 'หา',
            'หวิข้าว': 'หิวข้าว',
            'เซเวน': 'เซเว่น',
            'ร้านาหาร': 'ร้านอาหาร',
            'เเจ้ง': 'แจ้ง',
            'เเก้': 'แก้'
        }
        
        # Apply typo corrections
        corrected_text = text
        for typo, correct in typo_map.items():
            corrected_text = corrected_text.replace(typo, correct)
        
        prompt = f"""Analyze this Thai query and extract 3-5 search keywords for a condo knowledge base.

Query: "{corrected_text}"

Instructions:
1. Identify the USER'S INTENT (e.g., asking about food, facilities, rules, services)
2. Generate keywords that match the intent, even if not explicitly mentioned
3. Include related terms and synonyms

Examples:
- "หิวข้าว" or "หาอาหาร" → keywords: อาหาร ร้านอาหาร ร้านค้า เซเว่น ภัตตาคาร
- "จอดรถ" → keywords: จอดรถ ที่จอดรถ รถยนต์ ลานจอด
- "ฟิตเนส" → keywords: ฟิตเนส ออกกำลังกาย สระว่ายน้ำ สุขภาพ
- "กฎ" or "ระเบียบ" → keywords: กฎ ระเบียบ ข้อบังคับ ห้าม อนุญาต

Return ONLY the keywords separated by spaces (no explanation).
"""
        
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        keywords = res.text.strip().split()
        print(f"🔑 Enhanced Keywords: {keywords} (from: '{text}')")
        return keywords
    except Exception as e:
        print(f"AI Keyword Error: {e}")
        # Fallback with basic corrections
        corrected = text
        for typo, correct in typo_map.items():
            corrected = corrected.replace(typo, correct)
        return corrected.split()
