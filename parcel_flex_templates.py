"""
Parcel Flex Templates - Smart Condo Backend
Beautiful LINE Flex Message templates for parcel notifications
(No complaint system templates)
"""

def create_parcel_registered_flex(parcel_data):
    """
    Create flex message for new parcel notification
    """
    pin = parcel_data.get('pin', '-')
    transport = parcel_data.get('transport', 'ไม่ระบุ')
    tracking = parcel_data.get('tracking_number', '-')
    room = parcel_data.get('room_number', '-')
    recipient_name = parcel_data.get('recipient_name', '-')
    image_url = parcel_data.get('image_url', '')
    
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "📦 พัสดุมาใหม่!",
                    "color": "#FFFFFF",
                    "weight": "bold",
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
                    "text": pin,
                    "weight": "bold",
                    "size": "3xl",
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
                                    "text": "🏠 ห้อง",
                                    "color": "#aaaaaa",
                                    "size": "sm",
                                    "flex": 2
                                },
                                {
                                    "type": "text",
                                    "text": room,
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
                                    "text": "👤 ผู้รับ",
                                    "color": "#aaaaaa",
                                    "size": "sm",
                                    "flex": 2
                                },
                                {
                                    "type": "text",
                                    "text": recipient_name,
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
                                    "text": "📮 ขนส่ง",
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
                                    "text": "🔢 เลขพัสดุ",
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
            "spacing": "sm",
            "contents": [
                {
                    "type": "text",
                    "text": "แจ้ง PIN นี้กับเจ้าหน้าที่เมื่อมารับพัสดุค่ะ",
                    "color": "#666666",
                    "size": "xs",
                    "align": "center",
                    "wrap": True
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
            "aspectMode": "cover"
        }
    
    return bubble

def create_parcel_cancelled_flex(parcel_count):
    """
    Create flex message for parcel cancellation
    """
    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "✅ ยกเลิกสำเร็จ",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md"
                }
            ],
            "backgroundColor": "#6C757D",
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": f"ยกเลิกการลงทะเบียนรับนอกเวลา {parcel_count} รายการแล้วค่ะ",
                    "wrap": True,
                    "color": "#666666",
                    "size": "sm"
                }
            ]
        }
    }

def create_parcel_ask_selection_flex(parcels, room_number):
    """
    Create flex message for parcel selection (after-hours)
    """
    parcel_items = []
    
    for idx, p in enumerate(parcels, 1):
        pin = p.get('pin', '-')
        transport = p.get('transport', '-')
        tracking = p.get('tracking_number', '-')
        
        parcel_items.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "md",
            "contents": [
                {
                    "type": "text",
                    "text": f"{idx}.",
                    "size": "sm",
                    "color": "#666666",
                    "flex": 0
                },
                {
                    "type": "box",
                   "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"PIN: {pin}",
                            "weight": "bold",
                            "size": "sm",
                            "color": "#333333"
                        },
                        {
                            "type": "text",
                            "text": f"{transport} | {tracking}",
                            "size": "xs",
                            "color": "#999999",
                            "wrap": True
                        }
                    ],
                    "flex": 1
                }
            ]
        })
    
    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "📝 เลือกพัสดุรับนอกเวลา",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md"
                },
                {
                    "type": "text",
                    "text": f"ห้อง {room_number}",
                    "color": "#FFFFFF",
                    "size": "xs",
                    "margin": "sm"
                }
            ],
            "backgroundColor": "#007BFF",
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": parcel_items
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "พิมพ์ตัวเลขเพื่อเลือก (เช่น 1, 2) หรือ 'ทั้งหมด'",
                    "color": "#aaaaaa",
                    "size": "xs",
                    "align": "center",
                    "wrap": True
                }
            ]
        }
    }

def create_number_confirmation_flex(number_input):
    """
    Create flex message for number input confirmation
    """
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": f"คุณพิมพ์: {number_input}",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#333333"
                },
                {
                    "type": "text",
                    "text": "ต้องการลงทะเบียนรับพัสดุนอกเวลาใช่ไหมคะ?",
                    "wrap": True,
                    "color": "#666666",
                    "size": "sm",
                    "margin": "md"
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "action": {
                        "type": "message",
                        "label": "✅ ใช่",
                        "text": "ใช่"
                    }
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "action": {
                        "type": "message",
                        "label": "❌ ไม่ใช่",
                        "text": "ยกเลิก"
                    },
                    "margin": "sm"
                }
            ]
        }
    }

def create_parcel_status_flex(parcels, room_number):
    """
    Create flex message showing parcel status
    """
    parcel_items = []
    
    for idx, p in enumerate(parcels, 1):
        pin = p.get('pin', '-')
        transport = p.get('transport', '-')
        tracking = p.get('tracking_number', '-')
        
        parcel_items.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "md",
            "contents": [
                {
                    "type": "text",
                    "text": f"{idx}.",
                    "size": "sm",
                    "color": "#666666",
                    "flex": 0
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"PIN: {pin}",
                            "weight": "bold",
                            "size": "sm",
                            "color": "#333333"
                        },
                        {
                            "type": "text",
                            "text": f"{transport} | {tracking}",
                            "size": "xs",
                            "color": "#999999",
                            "wrap": True
                        }
                    ],
                    "flex": 1
                }
            ]
        })
    
    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "📦 พัสดุคงค้าง",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md"
                },
                {
                    "type": "text",
                    "text": f"ห้อง {room_number}",
                    "color": "#FFFFFF",
                    "size": "xs",
                    "margin": "sm"
                }
            ],
            "backgroundColor": "#1DB446",
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": parcel_items if parcel_items else [
                {
                    "type": "text",
                    "text": "ไม่มีพัสดุคงค้างค่ะ",
                    "color": "#999999",
                    "size": "sm",
                    "align": "center"
                }
            ]
        }
    }

def create_confirm_pickup_flex(parcel_data, user_image_url=None, is_user_action=False):
    """
    Create flex message for successful parcel pickup
    Shows the user-submitted image if available (after-hours verification)
    """
    pin = parcel_data.get('pin', '-')
    transport = parcel_data.get('transport', '-')
    tracking = parcel_data.get('tracking_number', '-')
    room = parcel_data.get('room_number', '-')
    recipient_name = parcel_data.get('recipient_name', '-')
    is_after_hours = parcel_data.get('is_after_hours', False)
    
    # Use user verification image if available, otherwise use original parcel image
    display_image = user_image_url or parcel_data.get('image_url', '')
    
    header_text = "✅ ยืนยันรับของสำเร็จ!" if is_user_action else "✅ รับพัสดุสำเร็จ!"
    
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": header_text,
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
                    "text": "ขอบคุณที่รับพัสดุค่ะ 🙏",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#1DB446",
                    "align": "center"
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
                                    "text": "🏠 ห้อง",
                                    "color": "#aaaaaa",
                                    "size": "sm",
                                    "flex": 2
                                },
                                {
                                    "type": "text",
                                    "text": room,
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
                                    "text": "👤 ผู้รับ",
                                    "color": "#aaaaaa",
                                    "size": "sm",
                                    "flex": 2
                                },
                                {
                                    "type": "text",
                                    "text": recipient_name,
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
                                    "text": "🔑 PIN",
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
                                    "text": "📮 ขนส่ง",
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
                    "text": "🌙 รับนอกเวลา (หลัง 16:30 น.)" if is_after_hours else "ขอบคุณที่ใช้บริการค่ะ",
                    "color": "#FF9900" if is_after_hours else "#aaaaaa",
                    "size": "xs",
                    "align": "center",
                    "weight": "bold" if is_after_hours else "regular"
                }
            ]
        }
    }
    
    # Add hero image if available
    if display_image and display_image.strip():
        bubble["hero"] = {
            "type": "image",
            "url": display_image,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover"
        }
    
    return bubble
