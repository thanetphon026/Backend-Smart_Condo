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
        recipient_name = p.get('recipient_name', '-')
        image_url = p.get('image_url', '')
        
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
                                        "text": "ผู้รับ",
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
                "spacing": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": "กรุณาแจ้ง PIN นี้กับนิติบุคคล",
                        "color": "#666666",
                        "size": "xs",
                        "align": "center"
                    },
                    {
                        "type": "separator",
                        "margin": "sm"
                    },
                    {
                        "type": "text",
                        "text": "ℹ️ กรณีจะมารับนอกเวลา (18:00-22:00 น.)\nกรุณาแจ้งน้องบอทด้วยนะคะ",
                        "color": "#FF9900",
                        "size": "xxs",
                        "align": "center",
                        "wrap": True,
                        "margin": "sm"
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
    recipient_name = parcel.get('recipient_name', '-')
    image_url = parcel.get('image_url', '')
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
                                    "text": "ผู้รับ",
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

def create_after_hours_selection_flex(parcels, room_number):
    """
    สร้าง Flex Message สำหรับให้ user เลือกพัสดุที่จะรับนอกเวลา
    แสดงรายการแบบชัดเจนเพื่อให้ตอบเป็นตัวเลขได้ง่าย
    """
    parcel_items = []
    
    # Header box for instructions
    parcel_items.append({
        "type": "box",
        "layout": "vertical",
        "contents": [
            {
                "type": "text",
                "text": f"คุณมีพัสดุคงค้าง {len(parcels)} ชิ้น",
                "weight": "bold",
                "size": "md",
                "color": "#333333"
            },
            {
                "type": "text",
                "text": "กรุณาเลือกรายการที่ต้องการรับนอกเวลา",
                "size": "xs",
                "color": "#999999",
                "margin": "sm"
            }
        ],
        "margin": "md"
    })
    
    parcel_items.append({"type": "separator", "margin": "md"})
    
    # List of parcels
    for idx, p in enumerate(parcels, 1):
        pin = p.get('pin', '-')
        transport = p.get('transport', '-')
        tracking = p.get('tracking_number', '-')
        
        parcel_items.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "md",
            "spacing": "sm",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "width": "24px",
                    "height": "24px",
                    "cornerRadius": "12px",
                    "backgroundColor": "#007BFF",
                    "contents": [
                        {
                            "type": "text",
                            "text": str(idx),
                            "color": "#FFFFFF",
                            "size": "xs",
                            "align": "center",
                            "gravity": "center",
                            "weight": "bold"
                        }
                    ],
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
                            "text": f"{transport} ({tracking})",
                            "size": "xs",
                            "color": "#666666",
                            "margin": "xs",
                            "wrap": True
                        }
                    ],
                    "flex": 1
                }
            ]
        })
        
        if idx < len(parcels):
             parcel_items.append({"type": "separator", "margin": "md", "color": "#F0F0F0"})

    bubble = {
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
    
    return bubble

def create_after_hours_confirmation_flex(registered_parcels, total_pending, total_registered, room_number):
    """
    สร้าง Flex Message สำหรับยืนยันการลงทะเบียนรับนอกเวลา
    แสดงสรุปพัสดุที่ลงทะเบียนและสถานะทั้งหมด
    """
    remaining = total_pending - total_registered
    
    # สร้างรายการพัสดุที่ลงทะเบียน
    parcel_items = []
    for idx, p in enumerate(registered_parcels, 1):
        pin = p.get('pin', '-')
        transport = p.get('transport', '-')
        
        parcel_items.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": f"{idx}.",
                    "size": "sm",
                    "color": "#666666",
                    "flex": 0,
                    "margin": "none"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"PIN: {pin}",
                            "size": "sm",
                            "color": "#333333",
                            "weight": "bold",
                            "wrap": True
                        },
                        {
                            "type": "text",
                            "text": transport,
                            "size": "xs",
                            "color": "#999999",
                            "wrap": True
                        }
                    ],
                    "flex": 1,
                    "spacing": "xs"
                }
            ],
            "spacing": "sm",
            "margin": "md"
        })
    
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "✅ ลงทะเบียนนอกเวลาสำเร็จ",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md",
                    "align": "center"
                },
                {
                    "type": "text",
                    "text": f"ห้อง {room_number}",
                    "color": "#FFFFFF",
                    "size": "xs",
                    "align": "center",
                    "margin": "sm"
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
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📊 สรุปสถานะพัสดุ",
                            "weight": "bold",
                            "size": "lg",
                            "color": "#FF9900"
                        },
                        {
                            "type": "separator",
                            "margin": "md"
                        }
                    ]
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
                                    "text": "พัสดุทั้งหมด",
                                    "color": "#aaaaaa",
                                    "size": "sm",
                                    "flex": 3
                                },
                                {
                                    "type": "text",
                                    "text": f"{total_pending} ชิ้น",
                                    "wrap": True,
                                    "color": "#666666",
                                    "size": "sm",
                                    "flex": 2,
                                    "align": "end",
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
                                    "text": "✅ ลงนอกเวลาแล้ว",
                                    "color": "#1DB446",
                                    "size": "sm",
                                    "flex": 3,
                                    "weight": "bold"
                                },
                                {
                                    "type": "text",
                                    "text": f"{total_registered} ชิ้น",
                                    "wrap": True,
                                    "color": "#1DB446",
                                    "size": "sm",
                                    "flex": 2,
                                    "align": "end",
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
                                    "text": "⏳ ยังไม่ได้ลง",
                                    "color": "#FF9900",
                                    "size": "sm",
                                    "flex": 3
                                },
                                {
                                    "type": "text",
                                    "text": f"{remaining} ชิ้น",
                                    "wrap": True,
                                    "color": "#FF9900",
                                    "size": "sm",
                                    "flex": 2,
                                    "align": "end",
                                    "weight": "bold"
                                }
                            ]
                        }
                    ]
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "lg",
                    "spacing": "xs",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"📦 พัสดุที่ลงทะเบียน ({len(registered_parcels)} ชิ้น)",
                            "weight": "bold",
                            "size": "sm",
                            "color": "#333333"
                        }
                    ] + parcel_items
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "🕐 เวลารับนอกเวลา",
                            "size": "xs",
                            "color": "#666666",
                            "weight": "bold"
                        },
                        {
                            "type": "text",
                            "text": "18:00-22:00 น. ที่ Lobby",
                            "size": "sm",
                            "color": "#FF9900",
                            "weight": "bold",
                            "margin": "xs"
                        }
                    ]
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": "ทางนิติบุคคลจะเตรียมพัสดุไว้ให้ค่ะ\nขอบคุณที่แจ้งล่วงหน้านะคะ 🙏",
                    "size": "xs",
                    "color": "#999999",
                    "align": "center",
                    "wrap": True,
                    "margin": "md"
                }
            ]
        }
    }
    
    return bubble

def create_after_hours_cancellation_flex(cancelled_parcels, remaining_count, room_number):
    """
    สร้าง Flex Message สำหรับยืนยันการยกเลิกรับนอกเวลา
    """
    cancelled_items = []
    
    for idx, p in enumerate(cancelled_parcels, 1):
        pin = p.get('pin', '-')
        transport = p.get('transport', '-')
        
        cancelled_items.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "❌",
                    "size": "xs",
                    "flex": 0,
                    "margin": "none",
                    "align": "center",
                    "gravity": "center"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"PIN: {pin}",
                            "size": "sm",
                            "color": "#333333",
                            "weight": "bold"
                        },
                        {
                            "type": "text",
                            "text": transport,
                            "size": "xs",
                            "color": "#999999"
                        }
                    ],
                    "flex": 1,
                    "margin": "sm"
                }
            ],
            "margin": "sm"
        })

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "ยกเลิกรับนอกเวลา",
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
            "backgroundColor": "#DC3545",
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": f"ยกเลิกแล้ว {len(cancelled_parcels)} รายการ",
                    "weight": "bold",
                    "size": "md",
                    "color": "#333333"
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "md",
                    "contents": cancelled_items
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "md",
                    "contents": [
                         {
                            "type": "text",
                            "text": f"📦 คงเหลือรายการนอกเวลา: {remaining_count} ชิ้น" if remaining_count > 0 else "✅ ไม่มีรายการรับนอกเวลาค้างแล้วครับ",
                            "size": "sm",
                            "color": "#FF9900" if remaining_count > 0 else "#1DB446",
                            "align": "center",
                            "weight": "bold"
                        }
                    ]
                }
            ]
        }
    }
    
    return bubble
