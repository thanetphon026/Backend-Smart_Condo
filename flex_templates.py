import datetime

def create_text_flex(text, title="Smart Condo Bot", color="#1DB446"):
    """
    สร้าง Flex Message แบบ Bubble สำหรับข้อความทั่วไป
    """
    return {
        "type": "bubble",
        "size": "giga",
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "20px",
            "backgroundColor": "#FFFFFF",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "width": "4px",
                            "height": "40px",
                            "backgroundColor": color,
                            "cornerRadius": "2px",
                            "margin": "none"
                        },
                        {
                            "type": "text",
                            "text": title,
                            "weight": "bold",
                            "color": color,
                            "size": "sm",
                            "flex": 1,
                            "gravity": "center",
                            "margin": "md"
                        }
                    ],
                    "margin": "none",
                    "alignItems": "center"
                },
                {
                    "type": "text",
                    "text": text,
                    "wrap": True,
                    "color": "#444444",
                    "size": "md",
                    "lineSpacing": "6px",
                    "margin": "md"
                }
            ]
        },
        "styles": {
            "footer": {
                "separator": True
            }
        }
    }

def create_parcel_carousel(parcels):
    """
    สร้าง Flex Message แบบ Carousel สำหรับรายการพัสดุ
    """
    bubbles = []
    
    for p in parcels:
        pin = p.get('pin', '-')
        transport = p.get('transport', 'ไม่ระบุ')
        tracking = p.get('tracking_number', '-')
        room = p.get('room_number', '-')
        
        # Determine icon/color based on transport (optional)
        header_color = "#FF9900" if "kerry" in transport.lower() else "#EF4C4C" if "post" in transport.lower() else "#1DB446"
        
        bubble = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "text",
                                "text": "📦 พัสดุมาใหม่",
                                "color": "#FFFFFF",
                                "weight": "bold",
                                "size": "sm"
                            },
                            {
                                "type": "text",
                                "text": f"ห้อง {room}",
                                "color": "#FFFFFF",
                                "align": "end",
                                "size": "xs"
                            }
                        ]
                    }
                ],
                "backgroundColor": header_color,
                "paddingTop": "15px",
                "paddingBottom": "15px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": pin,
                        "weight": "bold",
                        "size": "4xl",
                        "align": "center",
                        "color": "#333333",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": "รหัสรับพัสดุ (PIN)",
                        "size": "xs",
                        "color": "#aaaaaa",
                        "align": "center",
                        "margin": "xs"
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "ขนส่ง",
                                        "color": "#aaaaaa",
                                        "size": "sm",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": transport,
                                        "wrap": True,
                                        "color": "#666666",
                                        "size": "sm",
                                        "flex": 4,
                                        "weight": "bold"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "เลขพัสดุ",
                                        "color": "#aaaaaa",
                                        "size": "sm",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": tracking,
                                        "wrap": True,
                                        "color": "#666666",
                                        "size": "sm",
                                        "flex": 4
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                     {
                        "type": "text",
                        "text": "กรุณาแจ้ง PIN นี้กับนิติบุคคล",
                        "color": "#aaaaaa",
                        "size": "xs",
                        "align": "center"
                    }
                ]
            }
        }
        bubbles.append(bubble)
        
    return {
        "type": "carousel",
        "contents": bubbles
    }

def create_complaint_update_flex(status, description, room, message):
    """
    สร้าง Flex Message แจ้งอัพเดตสถานะร้องเรียน
    """
    status_color = "#EF4C4C" # Default pending
    status_text = "รับเรื่องแล้ว"
    
    if status == "resolved":
        status_color = "#1DB446"
        status_text = "ดำเนินการเสร็จสิ้น"
    elif status == "pending":
        status_color = "#FF9900"
        status_text = "กำลังดำเนินการ"
        
    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "📝 แจ้งสถานะร้องเรียน",
                    "weight": "bold",
                    "color": "#FFFFFF",
                     "size": "sm"
                },
                 {
                    "type": "text",
                    "text": f"ห้อง {room}",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "align": "end",
                     "size": "xs"
                }
            ],
            "backgroundColor": status_color,
             "paddingAll": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": status_text,
                    "weight": "bold",
                    "size": "xl",
                    "color": status_color,
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": description,
                    "size": "sm",
                    "color": "#555555",
                    "wrap": True,
                    "margin": "md",
                    "maxLines": 3
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": message,
                    "wrap": True,
                    "color": "#666666",
                    "size": "sm",
                    "margin": "lg"
                }
            ]
        }
    }
