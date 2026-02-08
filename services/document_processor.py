import json
import logging
import base64
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image
import io

logger = logging.getLogger(__name__)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}


def validate_document_format(filename: str) -> bool:
    """Check if file has valid extension"""
    if not filename:
        return False
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in ALLOWED_EXTENSIONS


def is_camera_capture(data: str) -> bool:
    """Check if data is base64 camera image"""
    if not data or not isinstance(data, str):
        return False
    # Base64 data often starts with specific prefixes
    return data.startswith('data:image') or (len(data) > 100 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in data[:50]))


def convert_camera_to_image(base64_data: str) -> Tuple[Optional[Image.Image], Optional[str]]:
    """
    Convert base64 camera capture to PIL Image
    Returns: (image, error_message)
    """
    try:
        # Remove data URI prefix if present
        if ',' in base64_data:
            base64_data = base64_data.split(',', 1)[1]
        
        # Decode base64
        image_data = base64.b64decode(base64_data)
        image = Image.open(io.BytesIO(image_data))
        
        logger.info(f"Successfully converted camera capture to image: {image.size}")
        return image, None
    except Exception as e:
        error_msg = f"Failed to convert camera capture: {str(e)}"
        logger.error(error_msg)
        return None, error_msg


def save_uploaded_file(file_content: bytes, filename: str, worker_id: str, doc_type: str, 
                      upload_dir: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Save uploaded file to disk
    Returns: (file_path, error_message)
    """
    try:
        if not validate_document_format(filename):
            return None, f"Invalid file format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        
        # Create directory if not exists
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate safe filename
        ext = filename.rsplit('.', 1)[-1].lower()
        safe_filename = f"{worker_id}_{doc_type}.{ext}"
        file_path = upload_dir / safe_filename
        
        # Save file
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        logger.info(f"Saved document: {file_path}")
        return str(file_path), None
    except Exception as e:
        error_msg = f"Failed to save file: {str(e)}"
        logger.error(error_msg)
        return None, error_msg


def save_pil_image_to_file(image: Image.Image, worker_id: str, doc_type: str, 
                           upload_dir: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Save PIL Image to file
    Returns: (file_path, error_message)
    """
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = upload_dir / f"{worker_id}_{doc_type}.png"
        image.save(file_path, 'PNG')
        
        logger.info(f"Saved image: {file_path}")
        return str(file_path), None
    except Exception as e:
        error_msg = f"Failed to save image: {str(e)}"
        logger.error(error_msg)
        return None, error_msg


def get_document_type(file_path: str) -> str:
    """Return 'pdf' or 'image' based on file extension"""
    ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else ''
    return 'pdf' if ext == 'pdf' else 'image'
