"""
LINE Service Module - Smart Condo Backend
Handles LINE messaging and notifications
"""
from config import line_configuration
from linebot.v3.messaging import (
    ApiClient, MessagingApi,
    PushMessageRequest, TextMessage, ImageMessage, FlexMessage, FlexContainer
)

def send_line_message(user_id, message=None, image_url=None, flex_contents=None):
    """
    Send LINE message with support for text, image, and Flex messages
    Args:
        user_id: LINE User ID
        message: Text message
        image_url: Image URL
        flex_contents: Flex message dict
    Returns:
        bool: Success status
    """
    try:
        with ApiClient(line_configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            messages = []
            
            # 1. Flex Message
            if flex_contents:
                try:
                    flex_message = FlexMessage(
                        alt_text="ข้อความใหม่จาก Smart Condo",
                        contents=FlexContainer.from_dict(flex_contents)
                    )
                    messages.append(flex_message)
                except Exception as flex_err:
                    print(f"❌ Flex Construction Error: {flex_err}")
                    # Fallback to text
                    if message:
                        messages.append(TextMessage(text=message))
            
            # 2. Text Message
            elif message:
                messages.append(TextMessage(text=message))
            
            # 3. Image Message
            if image_url and image_url.strip():
                try:
                    messages.append(ImageMessage(
                        original_content_url=image_url,
                        preview_image_url=image_url
                    ))
                except Exception as img_error:
                    print(f"⚠️ Image Error: {img_error}")
            
            if not messages:
                return False

            try:
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=messages
                    )
                )
                print(f"✅ Message sent to {user_id}")
                return True
            except Exception as api_error:
                print(f"❌ LINE API Error: {api_error}")
                return False
                
    except Exception as e:
        print(f"❌ LINE Send Error: {e}")
        return False

def send_parcel_notification(user_id, parcel_data, flex_template_func):
    """
    Send parcel notification using flex template
    Args:
        user_id: LINE User ID
        parcel_data: Parcel information dict
        flex_template_func: Function that generates flex message
    Returns:
        bool: Success status
    """
    try:
        flex_contents = flex_template_func(parcel_data)
        return send_line_message(
            user_id=user_id,
            flex_contents=flex_contents
        )
    except Exception as e:
        print(f"❌ Send Parcel Notification Error: {e}")
        return False

def reply_line_message(reply_token, message=None, flex_contents=None):
    """
    Reply to LINE message using reply token
    Args:
        reply_token: Reply token from event
        message: Text message or dict with 'text' and optional 'flex'
        flex_contents: Flex message dict
    Returns:
        bool: Success status
    """
    try:
        from linebot.v3.messaging import ReplyMessageRequest
        
        with ApiClient(line_configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            messages = []
            
            # Handle dict message format
            if isinstance(message, dict):
                if message.get('flex'):
                    flex_contents = message['flex']
                message = message.get('text')
            
            # Flex message
            if flex_contents:
                try:
                    flex_message = FlexMessage(
                        alt_text=message or "ข้อความใหม่",
                        contents=FlexContainer.from_dict(flex_contents)
                    )
                    messages.append(flex_message)
                except Exception as flex_err:
                    print(f"❌ Flex Error: {flex_err}")
                    if message:
                        messages.append(TextMessage(text=message))
            
            # Text message
            elif message:
                messages.append(TextMessage(text=message))
            
            if not messages:
                return False
            
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=messages
                )
            )
            print(f"✅ Reply sent")
            return True
            
    except Exception as e:
        print(f"❌ LINE Reply Error: {e}")
        return False
