"""
Image Service Module - Smart Condo Backend
Handles image upload, validation, and deletion with Cloudinary
"""
import cloudinary.uploader
from cloudinary.api import delete_resources_by_tag
import base64
import tempfile
import os

def upload_image_to_cloudinary(image_data, is_base64=False, tags=None):
    """
    Upload image to Cloudinary
    Args:
        image_data: File object or base64 string
        is_base64: Whether image_data is base64 encoded
        tags: List of tags for the image
    Returns:
        tuple: (success: bool, url_or_error: str)
    """
    try:
        upload_options = {
            "folder": "smart_condo",
            "resource_type": "image"
        }
        
        if tags:
            upload_options["tags"] = tags
        
        if is_base64:
            # Handle base64 encoded image
            result = cloudinary.uploader.upload(
                f"data:image/png;base64,{image_data}",
                **upload_options
            )
        else:
            # Handle file object
            result = cloudinary.uploader.upload(image_data, **upload_options)
        
        image_url = result.get('secure_url')
        print(f"✅ Image uploaded to Cloudinary: {image_url}")
        return True, image_url
        
    except Exception as e:
        print(f"❌ Cloudinary Upload Error: {e}")
        return False, str(e)

def upload_image_from_url(image_url, tags=None):
    """
    Upload image from URL to Cloudinary
    Args:
        image_url: URL of the image to upload
        tags: List of tags for the image
    Returns:
        tuple: (success: bool, url_or_error: str)
    """
    try:
        upload_options = {
            "folder": "smart_condo",
            "resource_type": "image"
        }
        
        if tags:
            upload_options["tags"] = tags
        
        result = cloudinary.uploader.upload(image_url, **upload_options)
        new_url = result.get('secure_url')
        print(f"✅ Image re-uploaded to Cloudinary: {new_url}")
        return True, new_url
        
    except Exception as e:
        print(f"❌ Cloudinary Re-upload Error: {e}")
        return False, str(e)

def delete_image_by_url(image_url):
    """
    Delete image from Cloudinary by URL
    Args:
        image_url: URL of the image to delete
    Returns:
        bool: Success status
    """
    try:
        if not image_url or "cloudinary.com" not in image_url:
            return False
        
        # Extract public_id from URL
        # URL format: https://res.cloudinary.com/{cloud_name}/image/upload/v{version}/{public_id}.{format}
        parts = image_url.split('/')
        if len(parts) >= 2:
            # Get the part after 'upload/'
            upload_index = parts.index('upload') if 'upload' in parts else -1
            if upload_index >= 0 and upload_index + 2 < len(parts):
                # Skip version (v1234567890) if present
                public_id_with_ext = '/'.join(parts[upload_index + 2:])
                # Remove file extension
                public_id = public_id_with_ext.rsplit('.', 1)[0]
                
                cloudinary.uploader.destroy(public_id)
                print(f"🗑️ Deleted image from Cloudinary: {public_id}")
                return True
        
        return False
    except Exception as e:
        print(f"⚠️ Cloudinary Delete Error: {e}")
        return False

def delete_images_by_tag(tag):
    """
    Delete all images with a specific tag from Cloudinary
    Args:
        tag: Tag to filter images
    Returns:
        int: Number of images deleted
    """
    try:
        result = delete_resources_by_tag(tag)
        deleted_count = len(result.get('deleted', {}))
        print(f"🗑️ Deleted {deleted_count} images with tag '{tag}' from Cloudinary")
        return deleted_count
    except Exception as e:
        print(f"⚠️ Cloudinary Batch Delete Error: {e}")
        return 0

def save_base64_to_temp_file(base64_data, extension='png'):
    """
    Save base64 image data to temporary file
    Args:
        base64_data: Base64 encoded image string
        extension: File extension
    Returns:
        str: Path to temporary file
    """
    try:
        # Decode base64
        image_bytes = base64.b64decode(base64_data)
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{extension}')
        temp_file.write(image_bytes)
        temp_file.close()
        
        return temp_file.name
    except Exception as e:
        print(f"❌ Base64 to File Error: {e}")
        return None
