"""
Flex Message Templates for Parcel Process
Color Scheme: Blue (#0084FF) for selection, Green (#1DB446) for success, Gray (#6C757D) for cancellation, Yellow (#FFC107) for confirmation
"""

def create_parcel_ask_selection_flex(parcels, total_pending, total_ah, total_normal, room_number):
    """
    สร้าง Flex Message สำหรับให้เลือกพัสดุที่ต้องการรับนอกเวลา
    Theme: Blue (#0084FF)
    """
    # Build parcel items
    parcel_contents = []
    for idx, p in enumerate(parcels[:5], 1):  # Limit to 5 items for display
        pin = p.get('pin', '-')
        transport = p.get('transport', '-')
        tracking = p.get('tracking_number', '-')
        
        parcel_contents.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": f"{idx}.",
                    "size": "sm",
                    "color": "#0084FF",
                    "weight": "bold",
                    "flex": 0
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
                            "text": f"{transport} • {tracking}",
                            "size": "xs",
                            "color": "#666666",
                            "wrap": True
                        }
                    ],
                    "flex": 1,
                    "margin": "md"
                }
            ],
            "margin": "md",
            "paddingAll": "8px",
            "backgroundColor": "#F0F8FF",
            "cornerRadius": "8px"
        })
    
    if len(parcels) > 5:
        parcel_contents.append({
            "type": "text",
            "text": f"... และอีก {len(parcels) - 5} รายการ",
            "size": "xs",
            "color": "#999999",
            "align": "center",
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
                    "text": "📦 ลงทะเบียนรับนอกเวลา",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md"
                }
            ],
            "backgroundColor": "#0084FF",
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": f"ห้อง {room_number}",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#0084FF",
                    "margin": "md"
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
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": str(total_pending),
                                    "size": "xl",
                                    "weight": "bold",
                                    "color": "#0084FF",
                                    "align": "center"
                                },
                                {
                                    "type": "text",
                                    "text": "ทั้งหมด",
                                    "size": "xs",
                                    "color": "#666666",
                                    "align": "center"
                                }
                            ],
                            "flex": 1
                        },
                        {
                            "type": "separator"
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": str(total_ah),
                                    "size": "xl",
                                    "weight": "bold",
                                    "color": "#1DB446",
                                    "align": "center"
                                },
                                {
                                    "type": "text",
                                    "text": "นอกเวลา",
                                    "size": "xs",
                                    "color": "#666666",
                                    "align": "center"
                                }
                            ],
                            "flex": 1
                        },
                        {
                            "type": "separator"
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": str(total_normal),
                                    "size": "xl",
                                    "weight": "bold",
                                    "color": "#FF9900",
                                    "align": "center"
                                },
                                {
                                    "type": "text",
                                    "text": "ปกติ",
                                    "size": "xs",
                                    "color": "#666666",
                                    "align": "center"
                                }
                            ],
                            "flex": 1
                        }
                    ],
                    "margin": "lg",
                    "paddingAll": "12px",
                    "backgroundColor": "#F8F8F8",
                    "cornerRadius": "8px"
                },
                {
                    "type": "text",
                    "text": "รายการพัสดุ:",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#333333",
                    "margin": "xl"
                }
            ] + parcel_contents + [
                {
                    "type": "separator",
                    "margin": "xl"
                },
                {
                    "type": "text",
                    "text": "กรุณาเลือกรายการที่ต้องการรับนอกเวลา:",
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
                            "text": "• พิมพ์ตัวเลข: 1, 2, 3",
                            "size": "xs",
                            "color": "#999999"
                        },
                        {
                            "type": "text",
                            "text": "• หรือพิมพ์: ทั้งหมด",
                            "size": "xs",
                            "color": "#999999"
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
    
    return bubble


def create_parcel_registered_flex(registered_parcels, total_pending, total_ah, room_number):
    """
    สร้าง Flex Message ยืนยันการลงทะเบียนพัสดุนอกเวลาสำเร็จ
    Theme: Green (#1DB446)
    """
    # Build registered items summary
    item_contents = []
    for p in registered_parcels[:3]:  # Show max 3
        pin = p.get('pin', '-')
        transport = p.get('transport', '-')
        item_contents.append({
            "type": "text",
            "text": f"• PIN {pin} ({transport})",
            "size": "sm",
            "color": "#333333",
            "wrap": True
        })
    
    if len(registered_parcels) > 3:
        item_contents.append({
            "type": "text",
            "text": f"... และอีก {len(registered_parcels) - 3} รายการ",
            "size": "xs",
            "color": "#999999"
        })
    
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "✅ ลงทะเบียนสำเร็จ",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md",
                    "flex": 1
                },
                {
                    "type": "text",
                    "text": f"ห้อง {room_number}",
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
                    "text": f"ลงทะเบียนรับนอกเวลา {len(registered_parcels)} ชิ้น",
                    "weight": "bold",
                    "size": "lg",
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
                    "contents": item_contents,
                    "margin": "lg",
                    "paddingAll": "12px",
                    "backgroundColor": "#F0FAF3",
                    "cornerRadius": "8px"
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
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": str(total_pending),
                                    "size": "xl",
                                    "weight": "bold",
                                    "color": "#0084FF",
                                    "align": "center"
                                },
                                {
                                    "type": "text",
                                    "text": "ทั้งหมด",
                                    "size": "xs",
                                    "color": "#666666",
                                    "align": "center"
                                }
                            ],
                            "flex": 1
                        },
                        {
                            "type": "separator"
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": str(total_ah),
                                    "size": "xl",
                                    "weight": "bold",
                                    "color": "#1DB446",
                                    "align": "center"
                                },
                                {
                                    "type": "text",
                                    "text": "นอกเวลา",
                                    "size": "xs",
                                    "color": "#666666",
                                    "align": "center"
                                }
                            ],
                            "flex": 1
                        }
                    ],
                    "margin": "lg",
                    "paddingAll": "12px",
                    "backgroundColor": "#F8F8F8",
                    "cornerRadius": "8px"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "🕐 เวลารับนอกเวลา",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#333333",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "18:00 - 22:00 น. ที่ Lobby ชั้น 1",
                    "size": "sm",
                    "color": "#666666",
                    "margin": "sm"
                },
                {
                    "type": "text",
                    "text": "ทางนิติบุคคลจะเตรียมพัสดุไว้ให้ค่ะ ขอบคุณที่แจ้งล่วงหน้านะคะ 🙏",
                    "wrap": True,
                    "color": "#666666",
                    "size": "sm",
                    "margin": "lg"
                }
            ]
        }
    }
    
    return bubble


def create_parcel_cancelled_flex(cancelled_parcels, remaining_ah, room_number):
    """
    สร้าง Flex Message ยืนยันการยกเลิกพัสดุนอกเวลา
    Theme: Gray (#6C757D)
    """
    item_contents = []
    for p in cancelled_parcels[:3]:
        pin = p.get('pin', '-')
        transport = p.get('transport', '-')
        item_contents.append({
            "type": "text",
            "text": f"• PIN {pin} ({transport})",
            "size": "sm",
            "color": "#333333",
            "wrap": True
        })
    
    if len(cancelled_parcels) > 3:
        item_contents.append({
            "type": "text",
            "text": f"... และอีก {len(cancelled_parcels) - 3} รายการ",
            "size": "xs",
            "color": "#999999"
        })
    
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "❌ ยกเลิกเรียบร้อย",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md",
                    "flex": 1
                },
                {
                    "type": "text",
                    "text": f"ห้อง {room_number}",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "align": "end",
                    "size": "sm"
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
                    "text": f"ยกเลิกรับนอกเวลา {len(cancelled_parcels)} ชิ้น",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#6C757D",
                    "margin": "md"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": item_contents,
                    "margin": "lg",
                    "paddingAll": "12px",
                    "backgroundColor": "#F8F8F8",
                    "cornerRadius": "8px"
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
                            "text": "คงเหลือรับนอกเวลา:",
                            "size": "sm",
                            "color": "#666666",
                            "flex": 2
                        },
                        {
                            "type": "text",
                            "text": f"{remaining_ah} ชิ้น",
                            "size": "sm",
                            "color": "#1DB446" if remaining_ah > 0 else "#999999",
                            "weight": "bold",
                            "align": "end",
                            "flex": 1
                        }
                    ],
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "พัสดุเหล่านี้จะกลับไปรับในเวลาปกติ 08:00-18:00 น. ค่ะ",
                    "wrap": True,
                    "color": "#666666",
                    "size": "sm",
                    "margin": "lg"
                }
            ]
        }
    }
    
    return bubble


def create_number_confirmation_flex(input_text):
    """
    สร้าง Flex Message สำหรับถามยืนยันเมื่อพิมพ์ตัวเลขเฉยๆ
    Theme: Yellow (#FFC107)
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
                    "text": "⚠️ ยืนยันการทำรายการ",
                    "weight": "bold",
                    "color": "#333333",
                    "size": "md"
                }
            ],
            "backgroundColor": "#FFC107",
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "คุณพิมพ์:",
                    "size": "xs",
                    "color": "#999999",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": input_text,
                            "size": "lg",
                            "weight": "bold",
                            "color": "#333333",
                            "align": "center"
                        }
                    ],
                    "margin": "sm",
                    "paddingAll": "12px",
                    "backgroundColor": "#FFF8E1",
                    "cornerRadius": "8px"
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "❓ คุณต้องการลงทะเบียนรับพัสดุนอกเวลาใช่ไหมคะ?",
                    "wrap": True,
                    "weight": "bold",
                    "size": "md",
                    "color": "#333333",
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "ตอบได้ 2 แบบ:",
                            "size": "xs",
                            "color": "#999999",
                            "weight": "bold"
                        },
                        {
                            "type": "text",
                            "text": "✅ ใช่ / ตกลง / ได้ / รับ",
                            "size": "sm",
                            "color": "#1DB446",
                            "margin": "sm"
                        },
                        {
                            "type": "text",
                            "text": "❌ ไม่ / ยกเลิก / ไม่รับ",
                            "size": "sm",
                            "color": "#DC3545",
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
                    "text": "💡 เพื่อความแม่นยำในการบริการ",
                    "color": "#aaaaaa",
                    "size": "xxs",
                    "align": "center"
                }
            ]
        }
    }
    
    return bubble


def create_parcel_status_flex(all_parcels, total_pending, total_ah, total_normal, room_number):
    """
    สร้าง Flex Message แสดงสถานะพัสดุ (สำหรับ CHECK_STATUS)
    Theme: Green (#1DB446) - Information display
    """
    # Build parcel list
    parcel_contents = []
    
    if total_pending > 0:
        for idx, p in enumerate(all_parcels[:5], 1):
            pin = p.get('pin', '-')
            transport = p.get('transport', '-')
            tracking = p.get('tracking_number', '-')
            is_ah = p.get('is_after_hours', False)
            
            parcel_contents.append({
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{idx}.",
                        "size": "sm",
                        "color": "#1DB446" if is_ah else "#FF9900",
                        "weight": "bold",
                        "flex": 0
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
                                "text": f"{transport} • {tracking}",
                                "size": "xs",
                                "color": "#666666",
                                "wrap": True
                            }
                        ],
                        "flex": 1,
                        "margin": "md"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "นอกเวลา" if is_ah else "ปกติ",
                                "size": "xxs",
                                "color": "#FFFFFF",
                                "align": "center",
                                "weight": "bold"
                            }
                        ],
                        "backgroundColor": "#1DB446" if is_ah else "#FF9900",
                        "cornerRadius": "4px",
                        "paddingAll": "4px",
                        "width": "50px"
                    }
                ],
                "margin": "md",
                "paddingAll": "8px",
                "backgroundColor": "#F8F8F8",
                "cornerRadius": "8px"
            })
        
        if len(all_parcels) > 5:
            parcel_contents.append({
                "type": "text",
                "text": f"... และอีก {len(all_parcels) - 5} รายการ",
                "size": "xs",
                "color": "#999999",
                "align": "center",
                "margin": "md"
            })
    else:
        parcel_contents.append({
            "type": "text",
            "text": "🎉 ไม่มีพัสดุค้างจ่าย",
            "size": "md",
            "color": "#1DB446",
            "align": "center",
            "weight": "bold"
        })
    
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "📊 สถานะพัสดุ",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md",
                    "flex": 1
                },
                {
                    "type": "text",
                    "text": f"ห้อง {room_number}",
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
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": str(total_pending),
                                    "size": "xl",
                                    "weight": "bold",
                                    "color": "#0084FF",
                                    "align": "center"
                                },
                                {
                                    "type": "text",
                                    "text": "ทั้งหมด",
                                    "size": "xs",
                                    "color": "#666666",
                                    "align": "center"
                                }
                            ],
                            "flex": 1
                        },
                        {
                            "type": "separator"
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": str(total_ah),
                                    "size": "xl",
                                    "weight": "bold",
                                    "color": "#1DB446",
                                    "align": "center"
                                },
                                {
                                    "type": "text",
                                    "text": "นอกเวลา",
                                    "size": "xs",
                                    "color": "#666666",
                                    "align": "center"
                                }
                            ],
                            "flex": 1
                        },
                        {
                            "type": "separator"
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": str(total_normal),
                                    "size": "xl",
                                    "weight": "bold",
                                    "color": "#FF9900",
                                    "align": "center"
                                },
                                {
                                    "type": "text",
                                    "text": "ปกติ",
                                    "size": "xs",
                                    "color": "#666666",
                                    "align": "center"
                                }
                            ],
                            "flex": 1
                        }
                    ],
                    "margin": "md",
                    "paddingAll": "12px",
                    "backgroundColor": "#F8F8F8",
                    "cornerRadius": "8px"
                }
            ] + ([
                {
                    "type": "text",
                    "text": "รายการพัสดุ:",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#333333",
                    "margin": "xl"
                }
            ] if total_pending > 0 else []) + parcel_contents
        }
    }
    
    return bubble
