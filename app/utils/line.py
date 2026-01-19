from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, 
    PushMessageRequest, TextMessage, ImageMessage, FlexMessage, FlexContainer
)
from ..config import Config

line_configuration = Configuration(access_token=Config.LINE_CHANNEL_ACCESS_TOKEN)
line_handler = WebhookHandler(Config.LINE_CHANNEL_SECRET)

def send_message(user_id, text=None, flex_contents=None, image_url=None):
    """
    Sends a PUSH message. Use this for notifications (Admin scan).
    Counts towards monthly 'Push Message' quota.
    """
    try:
        with ApiClient(line_configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            messages = _format_messages(text, flex_contents, image_url)
            if messages:
                line_bot_api.push_message(PushMessageRequest(to=user_id, messages=messages))
                return True
    except Exception as e:
        print(f"Line Push Error: {e}")
        return False

def reply_message(reply_token, text=None, flex_contents=None, image_url=None):
    """
    Sends a REPLY message. Use this for Webhook responses (Chat).
    FREE/Unlimited (Doesn't count towards Push quota).
    """
    try:
        if not reply_token: return False
        with ApiClient(line_configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            messages = _format_messages(text, flex_contents, image_url)
            if messages:
                line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=messages))
                return True
    except Exception as e:
        print(f"Line Reply Error: {e}")
        return False

def _format_messages(text, flex_contents, image_url):
    messages = []
    if flex_contents:
        try:
            messages.append(FlexMessage(
                alt_text="การแจ้งเตือนพัสดุ",
                contents=FlexContainer.from_dict(flex_contents)
            ))
        except Exception as e:
            print(f"Flex Formatting Error: {e}")
            messages.append(TextMessage(text=text or "ข้อมูลแสดงผลผิดพลาด"))
    elif text:
        messages.append(TextMessage(text=text))
        
    if image_url:
        messages.append(ImageMessage(original_content_url=image_url, preview_image_url=image_url))
    return messages

# Flex Templates
def create_block_card(title, status, details, image_url=None, confirm_action=None, reject_action=None, color="#1DB446"):
    """
    Generic Block Card used for Parcel Confirmation/Warnings.
    """
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": title, "weight": "bold", "color": "#ffffff", "size": "xl"}
            ],
            "backgroundColor": color,
            "paddingAll": "20px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": []
        }
    }
    
    if image_url:
        bubble["body"]["contents"].append({
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
            "action": {"type": "uri", "uri": image_url}
        })
    
    info_box = {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {"type": "text", "text": status, "weight": "bold", "size": "lg", "color": color, "wrap": True},
            {"type": "separator", "margin": "md"},
            {"type": "text", "text": details, "wrap": True, "margin": "md", "size": "sm", "color": "#555555"}
        ],
        "paddingAll": "15px"
    }
    bubble["body"]["contents"].append(info_box)
    
    footer = {"type": "box", "layout": "vertical", "spacing": "sm", "contents": []}
    if confirm_action:
        footer["contents"].append({"type": "button", "style": "primary", "color": color, "action": confirm_action, "height": "sm"})
    if reject_action:
        footer["contents"].append({"type": "button", "style": "secondary", "action": reject_action, "height": "sm"})
    if footer["contents"]:
        bubble["footer"] = footer
        
    return bubble

def create_new_parcel_notification(room_number, recipient_name, transport, tracking_number, scan_time, total_pending, image_url=None):
    """
    Header: พัสดุใหม่
    Body: Details + Image + Total Pending + Instruction
    """
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "📦 พัสดุมาใหม่", "weight": "bold", "color": "#ffffff", "size": "lg"}
            ],
            "backgroundColor": "#007bff",
            "paddingAll": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": []
        }
    }

    if image_url:
        bubble["body"]["contents"].append({
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
            "margin": "md",
            "action": {
                "type": "uri",
                "uri": image_url
            }
        })

    details_box = {
        "type": "box",
        "layout": "vertical",
        "margin": "lg",
        "spacing": "sm",
        "contents": [
            {"type": "text", "text": f"🏠 เลขห้อง: {room_number}", "weight": "bold", "size": "sm", "wrap": True},
            {"type": "text", "text": f"👤 ชื่อผู้รับ: {recipient_name}", "size": "sm", "wrap": True},
            {"type": "text", "text": f"🚚 บริษัทขนส่ง: {transport}", "size": "sm", "wrap": True},
            {"type": "text", "text": f"📦 เลขพัสดุ: {tracking_number}", "size": "sm", "wrap": True},
            {"type": "text", "text": f"⏰ เวลาที่บันทึก: {scan_time}", "size": "xs", "color": "#aaaaaa", "wrap": True},
            {"type": "separator", "margin": "md"},
            {"type": "text", "text": f"📊 พัสดุค้างทั้งหมด: {total_pending} ชิ้น", "weight": "bold", "size": "sm", "color": "#007bff", "margin": "md"},
            {"type": "box", "layout": "vertical", "margin": "md", "backgroundColor": "#fff4e5", "paddingAll": "10px", "cornerRadius": "md", "contents": [
                {"type": "text", "text": "🔔 ต้องการรับนอกเวลา?", "weight": "bold", "size": "xs", "color": "#b45d00"},
                {"type": "text", "text": "ให้แจ้งภายใน 08:00-16:30 น. ของทุกวัน", "size": "xs", "color": "#b45d00", "wrap": True}
            ]}
        ]
    }
    bubble["body"]["contents"].append(details_box)
    
    bubble["footer"] = {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {
                "type": "button",
                "style": "primary",
                "color": "#007bff",
                "action": {"type": "postback", "label": "ลงทะเบียนรับนอกเวลา", "data": "action=register_outside_trigger"},
                "height": "sm"
            }
        ]
    }
    return bubble

def create_premium_parcel_list(parcels_list, title="📦 รายการพัสดุทั้งหมด", header_color="#0066ff"):
    """
    Premium Unified Parcel List Card.
    Used for both 'Check Status' and 'Selection'.
    """
    total = len(parcels_list)
    outside = sum(1 for p in parcels_list if p.get('is_after_hours'))
    in_time = total - outside

    bubble = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": title, "weight": "bold", "color": "#ffffff", "size": "lg"}
            ],
            "backgroundColor": header_color,
            "paddingAll": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "box", "layout": "vertical", "contents": [
                            {"type": "text", "text": "ทั้งหมด", "size": "xs", "color": "#aaaaaa", "align": "center"},
                            {"type": "text", "text": str(total), "weight": "bold", "align": "center"}
                        ]},
                        {"type": "box", "layout": "vertical", "contents": [
                            {"type": "text", "text": "ในเวลา", "size": "xs", "color": "#aaaaaa", "align": "center"},
                            {"type": "text", "text": str(in_time), "weight": "bold", "align": "center", "color": "#28a745"}
                        ]},
                        {"type": "box", "layout": "vertical", "contents": [
                            {"type": "text", "text": "นอกเวลา", "size": "xs", "color": "#aaaaaa", "align": "center"},
                            {"type": "text", "text": str(outside), "weight": "bold", "align": "center", "color": "#fd7e14"}
                        ]}
                    ],
                    "margin": "md"
                },
                {"type": "separator", "margin": "lg"}
            ]
        }
    }

    list_box = {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "md", "contents": []}
    
    for i, p in enumerate(parcels_list, 1):
        is_outside = p.get('is_after_hours')
        status_label = "(นอกเวลา)" if is_outside else "(ในเวลา)"
        status_color = "#fd7e14" if is_outside else "#28a745"
        bg_color = "#fff8f3" if is_outside else "#f8fff9"
        
        item = {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": bg_color,
            "paddingAll": "10px",
            "cornerRadius": "md",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"{i}. PIN: {p.get('pin','-')}", "weight": "bold", "size": "sm", "flex": 3},
                        {"type": "text", "text": status_label, "size": "xs", "color": status_color, "flex": 2, "align": "end", "weight": "bold"}
                    ]
                },
                {
                    "type": "text", "text": f"🚚 {p.get('transport','-')} | {p.get('tracking_number','-')}", 
                    "size": "xs", "color": "#555555", "margin": "xs", "wrap": True
                }
            ]
        }
        list_box["contents"].append(item)
    
    bubble["body"]["contents"].append(list_box)
    
    # Contextual Footer
    footer_contents = []
    if in_time > 0:
        footer_contents.append({"type": "text", "text": "💡 ต้องการรับพัสดุชิ้นไหนนอกเวลา", "size": "xs", "color": "#888888", "align": "center", "margin": "md"})
        footer_contents.append({"type": "text", "text": "แจ้งลำดับพัสดุ หรือรหัส PIN ได้เลยค่ะ", "size": "xs", "color": "#888888", "align": "center"})
    elif outside > 0:
        footer_contents.append({"type": "text", "text": "🌙 พร้อมสำหรับการรับนอกเวลาแล้วค่ะ", "size": "xs", "color": "#fd7e14", "align": "center", "margin": "md"})
        
    if footer_contents:
        bubble["footer"] = {"type": "box", "layout": "vertical", "contents": footer_contents, "paddingBottom": "10px"}
    
    return bubble

def create_cancellation_confirmation_card(parcels_to_cancel):
    """
    Card to confirm after-hours cancellation.
    """
    import datetime
    timestamp = int(datetime.datetime.utcnow().timestamp())
    p_names = [f"PIN: {p.get('pin')} ({p.get('transport')})" for p in parcels_to_cancel]
    details = "\n".join(p_names)
    pins = ",".join([str(p.get('pin')) for p in parcels_to_cancel])

    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "⚠️ ยืนยันการยกเลิก", "weight": "bold", "color": "#ffffff", "size": "lg"}
            ],
            "backgroundColor": "#ff9900",
            "paddingAll": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "คุณต้องการยกเลิกการนัดหมายรับพัสดุนอกเวลาสำหรับรายการดังต่อไปนี้ ใช่หรือไม่?", "wrap": True, "size": "sm"},
                {"type": "box", "layout": "vertical", "margin": "md", "backgroundColor": "#fff4e5", "paddingAll": "10px", "cornerRadius": "md", "contents": [
                    {"type": "text", "text": details, "size": "xs", "color": "#b45d00", "wrap": True}
                ]},
                {"type": "text", "text": "*พัสดุจะถูกย้ายกลับเข้าสู่ระบบรับในเวลาปกติ", "size": "xxs", "color": "#aaaaaa", "margin": "md"}
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
                    "color": "#ff9900",
                    "action": {"type": "postback", "label": "ยืนยันยกเลิก", "data": f"action=cancel_after_hours_confirm&pins={pins}&ts={timestamp}"},
                    "height": "sm"
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "action": {"type": "postback", "label": "รักษาสิทธิ์ไว้", "data": "action=cancel_abort"},
                    "height": "sm"
                }
            ]
        }
    }

def create_registration_confirmation_card(parcels_to_register):
    """
    Card to confirm after-hours registration.
    """
    import datetime
    timestamp = int(datetime.datetime.utcnow().timestamp())
    p_names = [f"PIN: {p.get('pin')} ({p.get('transport')})" for p in parcels_to_register]
    details = "\n".join(p_names)
    pins = ",".join([str(p.get('pin')) for p in parcels_to_register])

    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "🌙 ยืนยันการลงทะเบียน", "weight": "bold", "color": "#ffffff", "size": "lg"}
            ],
            "backgroundColor": "#6200ee",
            "paddingAll": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "คุณต้องการลงทะเบียนรับพัสดุนอกเวลาสำหรับรายการดังต่อไปนี้ ใช่หรือไม่?", "wrap": True, "size": "sm"},
                {"type": "box", "layout": "vertical", "margin": "md", "backgroundColor": "#f3e5f5", "paddingAll": "10px", "cornerRadius": "md", "contents": [
                    {"type": "text", "text": details, "size": "xs", "color": "#4a148c", "wrap": True}
                ]},
                {"type": "text", "text": "*พัสดุจะพร้อมรับที่จุดรับของนอกเวลา", "size": "xxs", "color": "#aaaaaa", "margin": "md"}
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
                    "color": "#6200ee",
                    "action": {"type": "postback", "label": "ยืนยันลงทะเบียน", "data": f"action=register_after_hours_confirm&pins={pins}&ts={timestamp}"},
                    "height": "sm"
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "action": {"type": "postback", "label": "ยกเลิก", "data": "action=register_abort"},
                    "height": "sm"
                }
            ]
        }
    }

def create_pickup_complete_card(room_number, recipient_name, transport, tracking_number, total_remaining, image_url=None):
    """
    Header: รับพัสดุเสร็จสิ้น
    """
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "✅ รับพัสดุเสร็จสิ้น", "weight": "bold", "color": "#ffffff", "size": "lg"}
            ],
            "backgroundColor": "#28a745",
            "paddingAll": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": []
        }
    }

    if image_url:
        bubble["body"]["contents"].append({
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
            "margin": "md",
            "action": {
                "type": "uri",
                "uri": image_url
            }
        })

    details_box = {
        "type": "box",
        "layout": "vertical",
        "margin": "lg",
        "spacing": "sm",
        "contents": [
            {"type": "text", "text": f"🏠 เลขห้อง: {room_number}", "weight": "bold", "size": "sm"},
            {"type": "text", "text": f"👤 ชื่อผู้รับ: {recipient_name}", "size": "sm"},
            {"type": "text", "text": f"🚚 ขนส่ง: {transport}", "size": "sm"},
            {"type": "text", "text": f"📦 เลขพัสดุ: {tracking_number}", "size": "sm"},
            {"type": "separator", "margin": "md"},
            {"type": "text", "text": f"📊 พัสดุคงค้างปัจจุบัน: {total_remaining} ชิ้น", "weight": "bold", "size": "sm", "color": "#28a745", "margin": "md"},
            {"type": "text", "text": "🙏 ขอบคุณที่ใช้บริการค่ะ", "size": "sm", "color": "#555555", "margin": "md", "align": "center"}
        ]
    }
    bubble["body"]["contents"].append(details_box)
    return bubble

def create_status_card(title, status_text, color="#06c755"):
    return {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": title, "weight": "bold", "size": "xl", "color": color, "align": "center"},
                {"type": "separator", "margin": "lg"},
                {"type": "text", "text": status_text, "margin": "lg", "wrap": True, "align": "center", "size": "md"}
            ],
            "paddingAll": "25px"
        }
    }

def create_image_error_card(reason, detail):
    """
    Warning card for image validation errors (size/extension).
    """
    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "❌ ไม่สามารถส่งรูปได้", "weight": "bold", "color": "#ffffff", "size": "lg"}
            ],
            "backgroundColor": "#ff3333",
            "paddingAll": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": reason, "weight": "bold", "size": "md", "color": "#ff3333", "wrap": True},
                {"type": "separator", "margin": "md"},
                {"type": "box", "layout": "vertical", "margin": "md", "spacing": "xs", "contents": [
                    {"type": "text", "text": f"📋 รายละเอียด: {detail}", "size": "sm", "wrap": True},
                    {"type": "text", "text": "✅ สิ่งที่คุณต้องทำ:", "weight": "bold", "size": "xs", "color": "#555555", "margin": "md"},
                    {"type": "text", "text": "• ขนาดไฟล์ต้องไม่เกิน 10 MB", "size": "xs", "color": "#555555"},
                    {"type": "text", "text": "• นามสกุลที่รองรับ: png, jpg, jpeg, heic, heif", "size": "xs", "color": "#555555"}
                ]}
            ]
        }
    }

def create_verification_result_card(is_match, reason, ocr_details, image_url, confirm_action=None):
    """
    Card to show AI Vision analysis result.
    """
    color = "#28a745" if is_match else "#dc3545"
    title = "✅ ยืนยันพัสดุถูกต้อง" if is_match else "❌ พัสดุไม่ถูกต้อง"
    
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": title, "weight": "bold", "color": "#ffffff", "size": "lg"}
            ],
            "backgroundColor": color,
            "paddingAll": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "image",
                    "url": image_url,
                    "size": "full",
                    "aspectRatio": "20:13",
                    "aspectMode": "cover",
                    "action": {
                        "type": "uri",
                        "uri": image_url
                    }
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "lg",
                    "spacing": "sm",
                    "contents": [
                        {"type": "text", "text": reason, "weight": "bold", "size": "md", "color": color, "wrap": True},
                        {"type": "separator", "margin": "md"},
                        {
                            "type": "box",
                            "layout": "vertical",
                            "margin": "md",
                            "spacing": "xs",
                            "contents": [
                                {"type": "text", "text": f"🏠 ห้องที่พบ: {ocr_details.get('room_number','-')}", "size": "sm"},
                                {"type": "text", "text": f"👤 ชื่อผู้รับ: {ocr_details.get('recipient_name','-')}", "size": "sm"},
                                {"type": "text", "text": f"🚚 ขนส่ง: {ocr_details.get('transport','-')}", "size": "sm"},
                                {"type": "text", "text": f"📦 เลขพัสดุ: {ocr_details.get('tracking_number','-')}", "size": "xs", "color": "#888888"}
                            ]
                        }
                    ]
                }
            ]
        }
    }

    if not is_match:
        warning_box = {
            "type": "box",
            "layout": "vertical",
            "margin": "md",
            "backgroundColor": "#fff5f5",
            "paddingAll": "10px",
            "cornerRadius": "md",
            "contents": [
                {"type": "text", "text": "⚠️ ไม่ใช่พัสดุของคุณ", "weight": "bold", "size": "xs", "color": "#dc3545"},
                {"type": "text", "text": "กรุณาวางพัสดุไว้ที่เดิม\nหรือตรวจสอบเลขห้องอีกครั้งค่ะ", "size": "xs", "color": "#dc3545", "wrap": True, "margin": "xs"}
            ]
        }
        bubble["body"]["contents"].append(warning_box)

    footer = {
        "type": "box",
        "layout": "vertical",
        "spacing": "sm",
        "contents": []
    }

    if is_match and confirm_action:
        footer["contents"].append({
            "type": "button",
            "style": "primary",
            "color": color,
            "action": confirm_action,
            "height": "sm"
        })
    else:
        # Disabled-look button for mismatch
        footer["contents"].append({
            "type": "button",
            "style": "secondary",
            "action": {"type": "postback", "label": "ยืนยัน (ปิดใช้งาน)", "data": "action=button_disabled"},
            "height": "sm"
        })

    footer["contents"].append({
        "type": "button",
        "style": "link",
        "action": {"type": "postback", "label": "ยกเลิก / ถ่ายใหม่", "data": "action=verify_retry"},
        "height": "sm"
    })
    
    bubble["footer"] = footer
    return bubble


def create_welcome_card(display_name=None, is_returning=False, user_info=None):
    """
    Welcome card for new users or returning users (after unblock).
    """
    if is_returning and user_info:
        # Returning user - show their info
        title = "🎉 ยินดีต้อนรับกลับ!"
        color = "#06c755"
        greeting = f"สวัสดีค่ะ คุณ{display_name or user_info.get('first_name', 'ลูกบ้าน')}!"
        
        bubble = {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": title, "weight": "bold", "color": "#ffffff", "size": "lg"}
                ],
                "backgroundColor": color,
                "paddingAll": "15px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": greeting, "weight": "bold", "size": "md", "wrap": True},
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": "📋 ข้อมูลของคุณในระบบ:", "weight": "bold", "size": "sm", "margin": "lg", "color": "#555555"},
                    {"type": "box", "layout": "vertical", "margin": "md", "backgroundColor": "#f0fff4", "paddingAll": "12px", "cornerRadius": "8px", "contents": [
                        {"type": "text", "text": f"🏠 ห้อง: {user_info.get('room_number', '-')}", "size": "sm", "color": "#333333"},
                        {"type": "text", "text": f"👤 ชื่อ: {user_info.get('first_name', '')} {user_info.get('last_name', '')}", "size": "sm", "color": "#333333", "margin": "xs"},
                        {"type": "text", "text": f"📱 เบอร์: {user_info.get('phone_number') or user_info.get('phone') or '-'}", "size": "sm", "color": "#333333", "margin": "xs"}
                    ]},
                    {"type": "text", "text": "พร้อมใช้งานแล้วค่ะ! พิมพ์ถามน้องบอตได้เลย 😊", "size": "xs", "color": "#888888", "margin": "lg", "wrap": True}
                ]
            }
        }
        return bubble
    else:
        # New user - prompt registration
        return create_registration_required_card(display_name)


def create_registration_required_card(display_name=None):
    """
    Card shown when user needs to register.
    """
    greeting = f"สวัสดีค่ะ คุณ{display_name}! 👋" if display_name else "สวัสดีค่ะ! 👋"
    
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "📝 กรุณาลงทะเบียน", "weight": "bold", "color": "#ffffff", "size": "lg"}
            ],
            "backgroundColor": "#6200ee",
            "paddingAll": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": greeting, "weight": "bold", "size": "md", "wrap": True},
                {"type": "text", "text": "ยินดีต้อนรับสู่ระบบแชทบอตนิติ ลุมพินีพาร์ค เพชรเกษม98 🏢", "size": "sm", "color": "#555555", "margin": "md", "wrap": True},
                {"type": "separator", "margin": "lg"},
                {"type": "text", "text": "⚠️ คุณยังไม่ได้ลงทะเบียนในระบบ", "weight": "bold", "size": "sm", "color": "#ff6600", "margin": "lg"},
                {"type": "text", "text": "กรุณาลงทะเบียนก่อนเพื่อใช้งานระบบค่ะ", "size": "sm", "color": "#555555", "margin": "sm", "wrap": True},
                {"type": "box", "layout": "vertical", "margin": "lg", "backgroundColor": "#f3e5f5", "paddingAll": "12px", "cornerRadius": "8px", "contents": [
                    {"type": "text", "text": "📌 วิธีลงทะเบียน:", "weight": "bold", "size": "sm", "color": "#6200ee"},
                    {"type": "text", "text": "พิมพ์ตามรูปแบบนี้:", "size": "xs", "color": "#666666", "margin": "sm"},
                    {"type": "text", "text": "ลงทะเบียน [เลขห้อง] [ชื่อ-สกุล] [เบอร์โทร]", "weight": "bold", "size": "sm", "color": "#4a148c", "margin": "sm", "wrap": True}
                ]},
                {"type": "box", "layout": "vertical", "margin": "md", "backgroundColor": "#e3f2fd", "paddingAll": "10px", "cornerRadius": "8px", "contents": [
                    {"type": "text", "text": "💡 ตัวอย่าง:", "weight": "bold", "size": "xs", "color": "#0066ff"},
                    {"type": "text", "text": "ลงทะเบียน 1234 สมชาย ใจดี 0812345678", "size": "xs", "color": "#333333", "margin": "xs", "wrap": True}
                ]}
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "📞 หากมีปัญหา ติดต่อนิติบุคคล", "size": "xxs", "color": "#aaaaaa", "align": "center"}
            ],
            "paddingAll": "10px"
        }
    }
    return bubble


def create_user_registration_success_card(room_number, full_name, phone):
    """
    Card shown after successful user registration.
    """
    bubble = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "✅ ลงทะเบียนสำเร็จ!", "weight": "bold", "color": "#ffffff", "size": "lg"}
            ],
            "backgroundColor": "#06c755",
            "paddingAll": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": f"ยินดีต้อนรับ คุณ{full_name}! 🎉", "weight": "bold", "size": "md", "wrap": True},
                {"type": "separator", "margin": "md"},
                {"type": "box", "layout": "vertical", "margin": "lg", "backgroundColor": "#f0fff4", "paddingAll": "12px", "cornerRadius": "8px", "contents": [
                    {"type": "text", "text": "📋 ข้อมูลที่ลงทะเบียน:", "weight": "bold", "size": "sm", "color": "#06c755"},
                    {"type": "text", "text": f"🏠 ห้อง: {room_number}", "size": "sm", "color": "#333333", "margin": "sm"},
                    {"type": "text", "text": f"👤 ชื่อ: {full_name}", "size": "sm", "color": "#333333", "margin": "xs"},
                    {"type": "text", "text": f"📱 เบอร์: {phone}", "size": "sm", "color": "#333333", "margin": "xs"}
                ]},
                {"type": "text", "text": "คุณสามารถใช้งานระบบได้แล้วค่ะ!", "size": "sm", "color": "#555555", "margin": "lg", "wrap": True},
                {"type": "box", "layout": "vertical", "margin": "md", "backgroundColor": "#fff8e1", "paddingAll": "10px", "cornerRadius": "8px", "contents": [
                    {"type": "text", "text": "💡 ทดลองใช้งาน:", "weight": "bold", "size": "xs", "color": "#ff8f00"},
                    {"type": "text", "text": "• พิมพ์ \"เช็คพัสดุ\" เช็คสถานะพัสดุ", "size": "xs", "color": "#333333", "margin": "xs"},
                    {"type": "text", "text": "• พิมพ์ \"ลงทะเบียนรับนอกเวลา\" นัดรับพัสดุ", "size": "xs", "color": "#333333", "margin": "xs"},
                    {"type": "text", "text": "• หรือถามคำถามเกี่ยวกับคอนโดได้เลย!", "size": "xs", "color": "#333333", "margin": "xs"}
                ]}
            ]
        }
    }
    return bubble

