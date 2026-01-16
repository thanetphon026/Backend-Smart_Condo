from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, 
    PushMessageRequest, TextMessage, ImageMessage, FlexMessage, FlexContainer
)
from ..config import Config

line_configuration = Configuration(access_token=Config.LINE_CHANNEL_ACCESS_TOKEN)
line_handler = WebhookHandler(Config.LINE_CHANNEL_SECRET)

def send_message(user_id, text=None, flex_contents=None, image_url=None):
    try:
        with ApiClient(line_configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            messages = []
            
            if flex_contents:
                try:
                    messages.append(FlexMessage(
                        alt_text="การแจ้งเตือนพัสดุ",
                        contents=FlexContainer.from_dict(flex_contents)
                    ))
                except Exception as e:
                    print(f"Flex Error: {e}")
                    messages.append(TextMessage(text=text or "เกิดข้อผิดพลาดในการแสดงผล"))
            
            elif text:
                messages.append(TextMessage(text=text))
                
            if image_url:
                messages.append(ImageMessage(original_content_url=image_url, preview_image_url=image_url))
                
            if messages:
                line_bot_api.push_message(PushMessageRequest(to=user_id, messages=messages))
                return True
    except Exception as e:
        print(f"Line Send Error: {e}")
        return False

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
                {
                    "type": "text",
                    "text": title,
                    "weight": "bold",
                    "color": "#ffffff",
                    "size": "xl"
                }
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
    
    # Image
    if image_url:
        bubble["body"]["contents"].append({
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
            "action": {"type": "uri", "uri": image_url}
        })
    
    # Details
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
    
    # Footer Buttons
    footer = {
        "type": "box",
        "layout": "vertical",
        "spacing": "sm",
        "contents": []
    }
    
    if confirm_action:
        # Check if disabled (handled by not adding action or making it a dull button)
        # But Line Flex doesn't support 'disabled' attribute easily. 
        # Usually we just don't show the button or show a grey button with no action.
        footer["contents"].append({
            "type": "button",
            "style": "primary",
            "color": color,
            "action": confirm_action,
            "height": "sm"
        })
        
    if reject_action:
        footer["contents"].append({
            "type": "button",
            "style": "secondary",
            "action": reject_action,
             "height": "sm"
        })
        
    if footer["contents"]:
        bubble["footer"] = footer
        
    return bubble
