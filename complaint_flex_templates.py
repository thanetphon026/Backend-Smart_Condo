def create_complaint_ask_details_flex():
    """
    สร้าง Flex Message สำหรับขอรายละเอียดการร้องเรียน
    """
    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "📝 แจ้งร้องเรียน",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md"
                }
            ],
            "backgroundColor": "#FF9900",
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "ยินดีรับใช้ค่ะ",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#FF9900",
                    "margin": "md"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "กรุณาพิมพ์รายละเอียดปัญหาที่พบมาได้เลยค่ะ",
                    "wrap": True,
                    "color": "#666666",
                    "size": "sm",
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "ตัวอย่าง:",
                            "size": "xs",
                            "color": "#999999",
                            "weight": "bold"
                        },
                        {
                            "type": "text",
                            "text": "• ไฟทางเดินชั้น 8 เสีย\n• แอร์ห้องไม่เย็น\n• น้ำรั่วที่ระเบียง",
                            "size": "xs",
                            "color": "#999999",
                            "wrap": True,
                            "margin": "sm"
                        }
                    ],
                    "margin": "lg",
                    "paddingAll": "12px",
                    "backgroundColor": "#F8F8F8",
                    "cornerRadius": "8px"
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "💡 หากต้องการยกเลิก พิมพ์ 'ยกเลิก'",
                    "color": "#aaaaaa",
                    "size": "xxs",
                    "align": "center"
                }
            ]
        }
    }

def create_complaint_ask_image_flex(description):
    """
    สร้าง Flex Message สำหรับขอรูปภาพประกอบการร้องเรียน
    """
    # Truncate description if too long
    display_desc = description[:80] + "..." if len(description) > 80 else description
    
    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "✅ บันทึกรายละเอียดแล้ว",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md"
                }
            ],
            "backgroundColor": "#1DB446",
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "รายละเอียดที่บันทึก:",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#333333",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": display_desc,
                            "size": "sm",
                            "color": "#666666",
                            "wrap": True
                        }
                    ],
                    "margin": "md",
                    "paddingAll": "12px",
                    "backgroundColor": "#F0F9FF",
                    "cornerRadius": "8px"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "📸 ขั้นตอนสุดท้าย",
                    "weight": "bold",
                    "size": "md",
                    "color": "#FF9900",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "กรุณาส่งรูปภาพหน้างานมาให้น้องบอทด้วยนะคะ เพื่อให้ช่างตรวจสอบได้ตรงจุด",
                    "wrap": True,
                    "color": "#666666",
                    "size": "sm",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📷 กดปุ่มรูปภาพ → เลือกรูป → ส่ง",
                            "size": "xs",
                            "color": "#999999",
                            "align": "center",
                            "weight": "bold"
                        }
                    ],
                    "margin": "md",
                    "paddingAll": "10px",
                    "backgroundColor": "#FFF4E6",
                    "cornerRadius": "8px"
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "💡 หากต้องการยกเลิก พิมพ์ 'ยกเลิก'",
                    "color": "#aaaaaa",
                    "size": "xxs",
                    "align": "center"
                }
            ]
        }
    }

def create_complaint_received_flex(description, image_url, priority, room):
    """
    สร้าง Flex Message ยืนยันการรับแจ้งร้องเรียน
    """
    # Map priority to color
    priority_colors = {
        "high": "#DC3545",
        "medium": "#FF9900",
        "low": "#1DB446"
    }
    priority_labels = {
        "high": "สูง",
        "medium": "กลาง",
        "low": "ต่ำ"
    }
    
    priority_lower = (priority or "low").lower()
    priority_color = priority_colors.get(priority_lower, "#1DB446")
    priority_label = priority_labels.get(priority_lower, "ต่ำ")
    
    # Truncate description
    display_desc = description[:60] + "..." if len(description) > 60 else description
    
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "✅ รับเรื่องเรียบร้อย",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md",
                    "flex": 1
                },
                {
                    "type": "text",
                    "text": f"ห้อง {room}",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "align": "end",
                    "size": "sm"
                }
            ],
            "backgroundColor": "#1DB446",
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "เรื่อง:",
                    "size": "xs",
                    "color": "#999999",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": display_desc,
                    "weight": "bold",
                    "size": "md",
                    "color": "#333333",
                    "wrap": True,
                    "margin": "sm"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "ระดับความสำคัญ:",
                            "size": "sm",
                            "color": "#666666",
                            "flex": 2
                        },
                        {
                            "type": "text",
                            "text": priority_label,
                            "size": "sm",
                            "color": priority_color,
                            "weight": "bold",
                            "align": "end",
                            "flex": 1
                        }
                    ],
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "สถานะ:",
                            "size": "sm",
                            "color": "#666666",
                            "flex": 2
                        },
                        {
                            "type": "text",
                            "text": "รอดำเนินการ",
                            "size": "sm",
                            "color": "#FF9900",
                            "weight": "bold",
                            "align": "end",
                            "flex": 1
                        }
                    ],
                    "margin": "md"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "เจ้าหน้าที่จะรีบดำเนินการตรวจสอบให้นะคะ ขอบคุณที่แจ้งค่ะ 🙏",
                    "wrap": True,
                    "color": "#666666",
                    "size": "sm",
                    "margin": "lg"
                }
            ]
        }
    }
    
    # Add hero image if available
    if image_url and image_url.strip():
        bubble["hero"] = {
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
            "action": {
                "type": "uri",
                "uri": image_url
            }
        }
    
    return bubble
