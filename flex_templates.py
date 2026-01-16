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

def create_after_hours_selection_flex(parcels, total_pending, total_ah, total_normal, room_number):
    """
    สร้าง Flex Message สำหรับให้ user เลือกพัสดุที่จะรับนอกเวลา
    แสดงสถิติและรายการพัสดุแยกประเภทชัดเจน
    """
    parcel_items = []
    
    # Section: Header Stats
    parcel_items.append({
        "type": "box",
        "layout": "vertical",
        "contents": [
            {
                "type": "text",
                "text": "📊 สรุปพัสดุคงค้าง",
                "weight": "bold",
                "size": "sm",
                "color": "#333333",
                "margin": "md"
            },
            {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "ทั้งหมด", "size": "xs", "color": "#aaaaaa", "align": "center"},
                            {"type": "text", "text": str(total_pending), "size": "xl", "color": "#333333", "weight": "bold", "align": "center"}
                        ]
                    },
                    {
                        "type": "separator",
                        "color": "#f0f0f0"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "ในเวลา", "size": "xs", "color": "#aaaaaa", "align": "center"},
                            {"type": "text", "text": str(total_normal), "size": "xl", "color": "#007BFF", "weight": "bold", "align": "center"}
                        ]
                    },
                    {
                        "type": "separator",
                        "color": "#f0f0f0"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "นอกเวลา", "size": "xs", "color": "#aaaaaa", "align": "center"},
                            {"type": "text", "text": str(total_ah), "size": "xl", "color": "#1DB446", "weight": "bold", "align": "center"}
                        ]
                    }
                ],
                "margin": "md"
            }
        ]
    })
    
    parcel_items.append({"type": "separator", "margin": "lg"})
    
    parcel_items.append({
        "type": "text",
        "text": "รายการพัสดุ (เลือกเพื่อย้ายไป 'รับนอกเวลา')",
        "size": "xs",
        "color": "#999999",
        "margin": "lg"
    })

    # List of parcels
    for idx, p in enumerate(parcels, 1):
        pin = p.get('pin', '-')
        transport = p.get('transport', '-')
        tracking = p.get('tracking_number', '-')
        is_ah = p.get('is_after_hours', False)
        
        # Determine status display
        status_color = "#1DB446" if is_ah else "#007BFF" # Green if AH, Blue if Normal
        status_text = "นอกเวลา" if is_ah else "ในเวลา"
        bg_color = "#E8F5E9" if is_ah else "#F6F6F6" # Light Green background for AH items

        parcel_items.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "md",
            "spacing": "sm",
            "paddingAll": "10px",
            "backgroundColor": bg_color,
            "cornerRadius": "8px",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "width": "24px",
                    "height": "24px",
                    "cornerRadius": "12px",
                    "backgroundColor": status_color,
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
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": f"PIN: {pin}",
                                    "weight": "bold",
                                    "size": "sm",
                                    "color": "#333333",
                                    "flex": 1
                                },
                                {
                                    "type": "text",
                                    "text": status_text,
                                    "size": "xxs",
                                    "color": status_color,
                                    "align": "end",
                                    "weight": "bold",
                                    "flex": 0
                                }
                            ]
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

def create_after_hours_error_flex(example_pin):
    """
    สร้าง Flex Message สำหรับแจ้งเตือนเมื่อ User พิมพ์ผิดในขั้นตอนเลือกพัสดุ
    """
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "❌ ไม่เข้าใจคำสั่ง",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md"
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
                    "text": "กรุณาเลือกด้วยวิธีใดวิธีหนึ่ง:",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#333333",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "md",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {"type": "text", "text": "1️⃣", "flex": 0, "size": "sm"},
                                {"type": "text", "text": "พิมพ์เลขลำดับ เช่น '1' หรือ '1,3'", "size": "sm", "color": "#666666", "margin": "sm", "wrap": True}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {"type": "text", "text": "2️⃣", "flex": 0, "size": "sm"},
                                {"type": "text", "text": f"พิมพ์ PIN เช่น '{example_pin}'", "size": "sm", "color": "#666666", "margin": "sm", "wrap": True}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {"type": "text", "text": "3️⃣", "flex": 0, "size": "sm"},
                                {"type": "text", "text": "พิมพ์ 'ทั้งหมด' เลือกทุกชิ้น", "size": "sm", "color": "#666666", "margin": "sm", "wrap": True}
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
                    "text": "หรือพิมพ์ 'ยกเลิก' เพื่อจบรายการ",
                    "color": "#aaaaaa",
                    "size": "xs",
                    "align": "center",
                    "wrap": True
                }
            ]
        }
    }
    return bubble

def create_parcel_status_flex(parcels, total_pending, total_ah, total_normal, room_number):
    """
    สร้าง Flex Message สำหรับ 'ตรวจสอบสถานะพัสดุ' (Green Theme)
    แสดงรายการพัสดุทั้งหมด แต่ไม่มีปุ่มกดเลือก (Info Only)
    """
    parcel_items = []
    
    # Section: Header Stats
    parcel_items.append({
        "type": "box",
        "layout": "vertical",
        "contents": [
            {
                "type": "text",
                "text": "📊 สถานะพัสดุของคุณ",
                "weight": "bold",
                "size": "sm",
                "color": "#333333",
                "margin": "md"
            },
            {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "ทั้งหมด", "size": "xs", "color": "#aaaaaa", "align": "center"},
                            {"type": "text", "text": str(total_pending), "size": "xl", "color": "#333333", "weight": "bold", "align": "center"}
                        ]
                    },
                    {
                        "type": "separator",
                        "color": "#f0f0f0"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "ในเวลา", "size": "xs", "color": "#aaaaaa", "align": "center"},
                            {"type": "text", "text": str(total_normal), "size": "xl", "color": "#007BFF", "weight": "bold", "align": "center"}
                        ]
                    },
                    {
                        "type": "separator",
                        "color": "#f0f0f0"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "นอกเวลา", "size": "xs", "color": "#aaaaaa", "align": "center"},
                            {"type": "text", "text": str(total_ah), "size": "xl", "color": "#1DB446", "weight": "bold", "align": "center"}
                        ]
                    }
                ],
                "margin": "md"
            }
        ]
    })
    
    parcel_items.append({"type": "separator", "margin": "lg"})
    
    # List of parcels
    if parcels:
        for idx, p in enumerate(parcels, 1):
            pin = p.get('pin', '-')
            transport = p.get('transport', '-')
            tracking = p.get('tracking_number', '-')
            is_ah = p.get('is_after_hours', False)
            
            # Determine status display
            status_color = "#1DB446" if is_ah else "#007BFF" 
            status_text = "นอกเวลา" if is_ah else "ในเวลา"
            bg_color = "#E8F5E9" if is_ah else "#F6F6F6"

            parcel_items.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "md",
                "spacing": "sm",
                "paddingAll": "10px",
                "backgroundColor": bg_color,
                "cornerRadius": "8px",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "width": "4px",
                        "backgroundColor": status_color,
                        "contents": [],
                        "flex": 0
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": f"PIN: {pin}",
                                        "weight": "bold",
                                        "size": "sm",
                                        "color": "#333333",
                                        "flex": 1
                                    },
                                    {
                                        "type": "text",
                                        "text": status_text,
                                        "size": "xxs",
                                        "color": status_color,
                                        "align": "end",
                                        "weight": "bold",
                                        "flex": 0
                                    }
                                ]
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
                        "flex": 1,
                        "paddingStart": "10px"
                    }
                ]
            })
    else:
         parcel_items.append({
            "type": "text",
            "text": "ไม่มีพัสดุคงค้างค่ะ",
            "size": "sm",
            "color": "#999999",
            "align": "center",
            "margin": "xl"
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
                    "text": "📦 ตรวจสอบพัสดุ",
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
            "backgroundColor": "#00A693",
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": parcel_items
        }
    }
    
    return bubble

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

def create_self_pickup_verification_flex(name, room, parcels, ai_data):
    """
    Create a Flex Message for confirming self-pickup verification.
    """
    parcel_items = []
    for p in parcels:
        parcel_items.append({
            "type": "box",
            "layout": "baseline",
            "spacing": "sm",
            "contents": [
                {
                    "type": "text",
                    "text": f"📦 PIN {p.get('pin')}",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#1a237e",
                    "flex": 0
                },
                {
                    "type": "text",
                    "text": f"{p.get('transport', '-')}",
                    "size": "sm",
                    "color": "#666666",
                    "wrap": True
                }
            ]
        })

    bubble = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "✅ ตรวจสอบรูปภาพสำเร็จ",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#06c755"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": f"ห้อง {room} - {name}",
                    "size": "md",
                    "weight": "bold",
                    "wrap": True
                },
                {
                    "type": "separator",
                    "margin": "sm"
                },
                {
                    "type": "text",
                    "text": "รายการพัสดุ:",
                    "size": "sm",
                    "color": "#aaaaaa",
                    "margin": "md"
                },
                *parcel_items,
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#f8f9fa",
                    "paddingAll": "10px",
                    "margin": "md",
                    "cornerRadius": "md",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"เหตุผล: {ai_data.get('reason', 'ตรวจสอบผ่านจากรูปภาพ')}",
                            "size": "sm",
                            "color": "#333333",
                            "wrap": True
                        }
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "color": "#06c755",
                    "action": {
                        "type": "postback",
                        "label": "ยืนยันรับของแล้ว",
                        "data": "action=confirm_self_pickup"
                    }
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "color": "#efefef",
                    "action": {
                        "type": "postback",
                        "label": "ยกเลิก",
                        "data": "action=cancel_self_pickup"
                    }
                }
            ]
        }
    }
    return bubble

def create_self_pickup_success_flex(count):
    """
    สร้าง Flex Message เมื่อยืนยันการรับพัสดุสำเร็จ
    """
    bubble = {
        "type": "bubble",
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
                            "text": "🎉 ยืนยันสำเร็จ!",
                            "weight": "bold",
                            "color": "#FFFFFF",
                            "size": "lg",
                            "align": "center"
                        }
                    ],
                    "backgroundColor": "#06c755",
                    "paddingAll": "15px",
                    "cornerRadius": "md"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"บันทึกการรับพัสดุจำนวน {count} ชิ้นเรียบร้อยแล้วค่ะ",
                            "weight": "bold",
                            "size": "sm",
                            "color": "#333333",
                            "wrap": True,
                            "align": "center",
                            "margin": "lg"
                        },
                        {
                            "type": "text",
                            "text": "ขอบคุณที่ใช้บริการค่ะ 🙏",
                            "size": "xs",
                            "color": "#666666",
                            "align": "center",
                            "margin": "md"
                        }
                    ],
                    "margin": "md"
                }
            ]
        }
    }
    return bubble

def create_self_pickup_mismatch_flex(reason):
    """
    Create a rich warning Flex Message for a mismatch in self-pickup verification.
    """
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#FF4B4B",
            "contents": [
                {
                    "type": "text",
                    "text": "⚠️ ตรวจสอบไม่ผ่าน",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#FFFFFF",
                    "align": "center"
                }
            ],
            "paddingAll": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": f"ขออภัยค่ะ {reason}",
                    "size": "md",
                    "weight": "bold",
                    "color": "#333333",
                    "wrap": True,
                    "align": "center"
                },
                {
                    "type": "text",
                    "text": "ข้อมูลพัสดุในรูปไม่ตรงกับข้อมูลห้องของคุณ หรือรูปภาพอาจจะไม่ชัดเจน",
                    "size": "sm",
                    "color": "#666666",
                    "wrap": True,
                    "align": "center"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#FFF5F5",
                    "paddingAll": "12px",
                    "cornerRadius": "md",
                    "margin": "lg",
                    "contents": [
                        {
                            "type": "text",
                            "text": "❗ กรุณาวางพัสดุคืนที่เดิม",
                            "color": "#FF4B4B",
                            "weight": "bold",
                            "size": "sm",
                            "align": "center"
                        },
                        {
                            "type": "text",
                            "text": "และตรวจสอบเลข PIN หรือหน้ากล่องใหม่อีกครั้งนะคะ",
                            "size": "xs",
                            "color": "#666666",
                            "align": "center",
                            "wrap": True,
                            "margin": "xs"
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
                    "text": "💡 ลองถ่ายรูปใหม่อีกครั้งให้ชัดเจนกว่าเดิม",
                    "size": "xxs",
                    "color": "#aaaaaa",
                    "align": "center"
                }
            ],
            "paddingAll": "md"
        }
    }
    return bubble

# ================= NEW: AFTER-HOURS PICKUP VERIFICATION TEMPLATES =================

def create_pickup_verification_success_flex(parcel, user_image_url, room_number):
    """
    สร้าง Flex Message สวยงามสำหรับการตรวจสอบพัสดุสำเร็จ
    แสดงรูปที่ผู้ใช้ถ่าย + ข้อมูลพัสดุที่ตรงกัน + ปุ่มยืนยันรับ
    """
    pin = parcel.get('pin', '-')
    transport = parcel.get('transport', '-')
    tracking = parcel.get('tracking_number', '-')
    recipient_name = parcel.get('recipient_name', '-')
    
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
                            "text": "✅ ตรวจสอบสำเร็จ",
                            "weight": "bold",
                            "color": "#FFFFFF",
                            "size": "lg",
                            "flex": 1
                        },
                        {
                            "type": "text",
                            "text": f"ห้อง {room_number}",
                            "color": "#FFFFFF",
                            "size": "sm",
                            "align": "end"
                        }
                    ]
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
                    "text": "🎉 นี่คือพัสดุของคุณ!",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#1DB446",
                    "margin": "md",
                    "align": "center"
                },
                {
                    "type": "text",
                    "text": "ข้อมูลตรงกับระบบ สามารถยืนยันรับได้เลยค่ะ",
                    "size": "sm",
                    "color": "#666666",
                    "align": "center",
                    "wrap": True,
                    "margin": "sm"
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
                    "backgroundColor": "#F8F9FA",
                    "cornerRadius": "md",
                    "paddingAll": "15px",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "baseline",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "📦 PIN",
                                    "color": "#aaaaaa",
                                    "size": "sm",
                                    "flex": 2
                                },
                                {
                                    "type": "text",
                                    "text": pin,
                                    "wrap": True,
                                    "color": "#333333",
                                    "size": "md",
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
                                    "color": "#333333",
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
                                    "text": "🚚 ขนส่ง",
                                    "color": "#aaaaaa",
                                    "size": "sm",
                                    "flex": 2
                                },
                                {
                                    "type": "text",
                                    "text": transport,
                                    "wrap": True,
                                    "color": "#333333",
                                    "size": "sm",
                                    "flex": 4
                                }
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "baseline",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "📋 เลขพัสดุ",
                                    "color": "#aaaaaa",
                                    "size": "sm",
                                    "flex": 2
                                },
                                {
                                    "type": "text",
                                    "text": tracking,
                                    "wrap": True,
                                    "color": "#666666",
                                    "size": "xs",
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
                    "type": "button",
                    "action": {
                        "type": "postback",
                        "label": "✅ ยืนยันรับพัสดุ",
                        "data": f"action=confirm_pickup&pin={pin}"
                    },
                    "style": "primary",
                    "color": "#1DB446",
                    "height": "sm"
                },
                {
                    "type": "button",
                    "action": {
                        "type": "postback",
                        "label": "❌ ยกเลิก",
                        "data": f"action=cancel_pickup&pin={pin}"
                    },
                    "style": "secondary",
                    "height": "sm"
                },
                {
                    "type": "text",
                    "text": "⏰ สามารถยืนยันได้ภายใน 24 ชั่วโมง",
                    "size": "xxs",
                    "color": "#aaaaaa",
                    "align": "center",
                    "margin": "md"
                }
            ]
        }
    }
    
    # Add user's photo as hero image
    if user_image_url and user_image_url.strip():
        bubble["hero"] = {
            "type": "image",
            "url": user_image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
            "action": {
                "type": "uri",
                "uri": user_image_url
            }
        }
    
    return bubble

def create_pickup_verification_failed_flex(reason, user_image_url=None):
    """
    สร้าง Flex Message สำหรับการตรวจสอบพัสดุไม่ผ่าน
    แสดงคำเตือนและคำแนะนำ (ปุ่มยืนยันถูกปิดใช้งาน)
    """
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "⚠️ ไม่ใช่พัสดุของคุณ",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "lg",
                    "align": "center"
                }
            ],
            "backgroundColor": "#FF4B4B",
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "❌ ตรวจสอบไม่ผ่าน",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#FF4B4B",
                    "margin": "md",
                    "align": "center"
                },
                {
                    "type": "text",
                    "text": reason,
                    "size": "sm",
                    "color": "#666666",
                    "align": "center",
                    "wrap": True,
                    "margin": "md"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#FFF5F5",
                    "cornerRadius": "md",
                    "paddingAll": "15px",
                    "margin": "lg",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📍 กรุณาดำเนินการ",
                            "weight": "bold",
                            "size": "sm",
                            "color": "#FF4B4B",
                            "margin": "none"
                        },
                        {
                            "type": "text",
                            "text": "1. วางพัสดุคืนที่เดิม\n2. ตรวจสอบเลข PIN หรือชื่อผู้รับ\n3. ถ่ายรูปใหม่ให้ชัดเจน",
                            "size": "xs",
                            "color": "#666666",
                            "wrap": True,
                            "margin": "md"
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#FFF9E6",
                    "cornerRadius": "md",
                    "paddingAll": "12px",
                    "margin": "md",
                    "contents": [
                        {
                            "type": "text",
                            "text": "💡 เคล็ดลับ",
                            "weight": "bold",
                            "size": "xs",
                            "color": "#FF9900"
                        },
                        {
                            "type": "text",
                            "text": "ถ่ายรูปให้เห็นฉลากพัสดุชัดเจน โดยเฉพาะชื่อผู้รับและเลขห้อง",
                            "size": "xxs",
                            "color": "#666666",
                            "wrap": True,
                            "margin": "xs"
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
                    "type": "button",
                    "action": {
                        "type": "message",
                        "label": "📸 ถ่ายรูปใหม่",
                        "text": "ถ่ายรูปพัสดุใหม่"
                    },
                    "style": "primary",
                    "color": "#007BFF",
                    "height": "sm"
                },
                {
                    "type": "text",
                    "text": "หรือติดต่อนิติบุคคล 02-689-6888",
                    "size": "xxs",
                    "color": "#aaaaaa",
                    "align": "center",
                    "margin": "md"
                }
            ]
        }
    }
    
    # Add user's photo as hero image if available
    if user_image_url and user_image_url.strip():
        bubble["hero"] = {
            "type": "image",
            "url": user_image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
            "action": {
                "type": "uri",
                "uri": user_image_url
            }
        }
    
    return bubble

def create_pickup_confirmed_flex(parcel, user_image_url, room_number):
    """
    สร้าง Flex Message สวยงามสำหรับยืนยันการรับพัสดุสำเร็จ
    """
    pin = parcel.get('pin', '-')
    transport = parcel.get('transport', '-')
    tracking = parcel.get('tracking_number', '-')
    recipient_name = parcel.get('recipient_name', '-')
    
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
                            "text": "🎉 รับพัสดุสำเร็จ",
                            "weight": "bold",
                            "color": "#FFFFFF",
                            "size": "lg",
                            "flex": 1
                        },
                        {
                            "type": "text",
                            "text": f"ห้อง {room_number}",
                            "color": "#FFFFFF",
                            "size": "sm",
                            "align": "end"
                        }
                    ]
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
                    "text": "✅ ยืนยันการรับพัสดุแล้ว",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#1DB446",
                    "margin": "md",
                    "align": "center"
                },
                {
                    "type": "text",
                    "text": "ขอบคุณที่ใช้บริการรับพัสดุนอกเวลาค่ะ",
                    "size": "sm",
                    "color": "#666666",
                    "align": "center",
                    "wrap": True,
                    "margin": "sm"
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
                    "backgroundColor": "#F0F9FF",
                    "cornerRadius": "md",
                    "paddingAll": "15px",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📦 รายละเอียดพัสดุ",
                            "weight": "bold",
                            "size": "sm",
                            "color": "#007BFF",
                            "margin": "none"
                        },
                        {
                            "type": "box",
                            "layout": "baseline",
                            "margin": "md",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "PIN",
                                    "color": "#aaaaaa",
                                    "size": "xs",
                                    "flex": 2
                                },
                                {
                                    "type": "text",
                                    "text": pin,
                                    "color": "#333333",
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
                                    "text": "ผู้รับ",
                                    "color": "#aaaaaa",
                                    "size": "xs",
                                    "flex": 2
                                },
                                {
                                    "type": "text",
                                    "text": recipient_name,
                                    "color": "#333333",
                                    "size": "xs",
                                    "flex": 4
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
                                    "size": "xs",
                                    "flex": 2
                                },
                                {
                                    "type": "text",
                                    "text": transport,
                                    "color": "#666666",
                                    "size": "xs",
                                    "flex": 4
                                }
                            ]
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#E8F5E9",
                    "cornerRadius": "md",
                    "paddingAll": "12px",
                    "margin": "md",
                    "contents": [
                        {
                            "type": "text",
                            "text": "✨ บันทึกการรับพัสดุเรียบร้อยแล้ว",
                            "weight": "bold",
                            "size": "xs",
                            "color": "#1DB446",
                            "align": "center"
                        },
                        {
                            "type": "text",
                            "text": f"เวลา: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')} น.",
                            "size": "xxs",
                            "color": "#666666",
                            "align": "center",
                            "margin": "xs"
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
                    "text": "🏠 Smart Condo - ระบบจัดการพัสดุอัจฉริยะ",
                    "size": "xxs",
                    "color": "#aaaaaa",
                    "align": "center"
                }
            ],
            "paddingAll": "md"
        }
    }
    
    # Add user's photo as hero image
    if user_image_url and user_image_url.strip():
        bubble["hero"] = {
            "type": "image",
            "url": user_image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
            "action": {
                "type": "uri",
                "uri": user_image_url
            }
        }
    
    return bubble

def create_system_closed_flex():
    """
    สร้าง Flex Message แจ้งว่าระบบรับนอกเวลาปิดแล้ว
    """
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "⏰ ระบบปิดรับลงทะเบียน",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "lg",
                    "align": "center"
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
                    "text": "ขณะนี้ปิดรับลงทะเบียนแล้วค่ะ",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#FF9900",
                    "margin": "md",
                    "align": "center"
                },
                {
                    "type": "text",
                    "text": "ระบบรับลงทะเบียนนอกเวลาปิดรับที่ 16:30 น. ทุกวัน",
                    "size": "sm",
                    "color": "#666666",
                    "align": "center",
                    "wrap": True,
                    "margin": "md"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#FFF9E6",
                    "cornerRadius": "md",
                    "paddingAll": "15px",
                    "margin": "lg",
                    "contents": [
                        {
                            "type": "text",
                            "text": "⏰ เวลาทำการ",
                            "weight": "bold",
                            "size": "sm",
                            "color": "#FF9900",
                            "margin": "none"
                        },
                        {
                            "type": "text",
                            "text": "• เปิดรับลงทะเบียน: 08:00 - 16:30 น.\n• รับพัสดุนอกเวลา: 18:00 - 22:00 น.",
                            "size": "xs",
                            "color": "#666666",
                            "wrap": True,
                            "margin": "md"
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#F0F9FF",
                    "cornerRadius": "md",
                    "paddingAll": "12px",
                    "margin": "md",
                    "contents": [
                        {
                            "type": "text",
                            "text": "💡 คำแนะนำ",
                            "weight": "bold",
                            "size": "xs",
                            "color": "#007BFF"
                        },
                        {
                            "type": "text",
                            "text": "กรุณาลงทะเบียนก่อน 16:30 น. เพื่อให้นิติบุคคลมีเวลาจัดเตรียมพัสดุให้ค่ะ",
                            "size": "xxs",
                            "color": "#666666",
                            "wrap": True,
                            "margin": "xs"
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
                    "text": "📞 สอบถามเพิ่มเติม: 02-689-6888",
                    "size": "xxs",
                    "color": "#aaaaaa",
                    "align": "center"
                }
            ],
            "paddingAll": "md"
        }
    }
    
    return bubble

