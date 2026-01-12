import datetime

def create_text_flex(text, title="Smart Condo Bot", color="#1DB446"):
    """
    สร้าง Flex Message แบบ Bubble สำหรับข้อความทั่วไป
    """
    return {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingTop": "20px",
            "paddingBottom": "20px",
            "paddingStart": "20px",
            "paddingEnd": "20px",
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
                            "cornerRadius": "2px"
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

def create_complaint_update_flex(status, description, room, message, image_url=None):
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
        
    bubble = {
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
            "paddingTop": "15px",
            "paddingBottom": "15px",
            "paddingStart": "15px",
            "paddingEnd": "15px"
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

    # Add Hero Image if available
    if image_url:
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

def create_parcel_pickup_flex(parcel, room):
    """
    สร้าง Flex Message สำหรับยืนยันการรับพัสดุ
    """
    pin = parcel.get('pin', '-')
    transport = parcel.get('transport', '-')
    tracking = parcel.get('tracking_number', '-')
    is_after_hours = parcel.get('is_after_hours', False)
    
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "✅ รับพัสดุสำเร็จ",
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
            "backgroundColor": "#1DB446",
            "paddingTop": "15px",
            "paddingBottom": "15px",
            "paddingStart": "15px",
            "paddingEnd": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "ขอบคุณที่รับพัสดุค่ะ",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#1DB446",
                    "margin": "md"
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
                                    "text": "PIN",
                                    "color": "#aaaaaa",
                                    "size": "sm",
                                    "flex": 2
                                },
                                {
                                    "type": "text",
                                    "text": pin,
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
                    "text": "รับนอกเวลา (18:00-22:00)" if is_after_hours else "ขอบคุณที่ใช้บริการค่ะ",
                    "color": "#FF9900" if is_after_hours else "#aaaaaa",
                    "size": "xs",
                    "align": "center",
                    "weight": "bold" if is_after_hours else "regular"
                }
            ]
        }
    }
    
    return bubble

def create_after_hours_selection_flex(parcels, room_number):
    """
    สร้าง Flex Message สำหรับแสดงรายการพัสดุเพื่อเลือกรับนอกเวลา
    แสดงเป็น Block Card เดียวที่รวมพัสดุทั้งหมด
    """
    parcel_count = len(parcels)
    
    # สร้างรายการพัสดุ
    parcel_items = []
    for idx, p in enumerate(parcels, 1):
        pin = p.get('pin', '-')
        transport = p.get('transport', '-')
        tracking = p.get('tracking_number', '-')
        
        # เพิ่ม separator ระหว่างพัสดุ
        if idx > 1:
            parcel_items.append({
                "type": "separator",
                "margin": "md"
            })
        
        # กล่องพัสดุแต่ละชิ้น
        parcel_items.append({
            "type": "box",
            "layout": "vertical",
            "margin": "md",
            "spacing": "sm",
            "contents": [
                {
                    "type": "text",
                    "text": f"📦 พัสดุที่ {idx}",
                    "weight": "bold",
                    "color": "#333333",
                    "size": "sm"
                },
                {
                    "type": "box",
                    "layout": "baseline",
                    "contents": [
                        {
                            "type": "text",
                            "text": "PIN:",
                            "color": "#aaaaaa",
                            "size": "xs",
                            "flex": 1
                        },
                        {
                            "type": "text",
                            "text": pin,
                            "wrap": True,
                            "color": "#666666",
                            "size": "xs",
                            "flex": 3,
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
                            "text": "ขนส่ง:",
                            "color": "#aaaaaa",
                            "size": "xs",
                            "flex": 1
                        },
                        {
                            "type": "text",
                            "text": transport,
                            "wrap": True,
                            "color": "#666666",
                            "size": "xs",
                            "flex": 3
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "baseline",
                    "contents": [
                        {
                            "type": "text",
                            "text": "Tracking:",
                            "color": "#aaaaaa",
                            "size": "xs",
                            "flex": 1
                        },
                        {
                            "type": "text",
                            "text": tracking,
                            "wrap": True,
                            "color": "#666666",
                            "size": "xs",
                            "flex": 3
                        }
                    ]
                }
            ]
        })
    
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
                            "text": "🕐 รับนอกเวลา",
                            "color": "#FFFFFF",
                            "weight": "bold",
                            "size": "sm"
                        },
                        {
                            "type": "text",
                            "text": f"ห้อง {room_number}",
                            "color": "#FFFFFF",
                            "align": "end",
                            "size": "xs"
                        }
                    ]
                },
                {
                    "type": "text",
                    "text": f"ทั้งหมด {parcel_count} ชิ้น",
                    "color": "#FFFFFF",
                    "size": "xs",
                    "margin": "sm"
                }
            ],
            "backgroundColor": "#FF9900",
            "paddingTop": "15px",
            "paddingBottom": "15px",
            "paddingStart": "15px",
            "paddingEnd": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "เลือกพัสดุที่ต้องการรับนอกเวลา",
                    "weight": "bold",
                    "size": "md",
                    "color": "#333333",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": "กรุณากดปุ่มด้านล่างเพื่อเลือก",
                    "size": "xs",
                    "color": "#aaaaaa",
                    "margin": "xs",
                    "wrap": True
                }
            ] + parcel_items
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "🕐 เวลารับ: 18:00-22:00 น. ที่ Lobby",
                    "color": "#aaaaaa",
                    "size": "xs",
                    "align": "center",
                    "wrap": True
                }
            ]
        }
    }
    
    return bubble
