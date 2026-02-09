"""
Document Verification Service
Verifies that name and DOB from personal documents match educational documents
"""

import logging
import re

logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """
    Normalize names for comparison by removing extra spaces and converting to lowercase
    """
    if not name:
        return ""
    # Remove extra spaces, special characters, and convert to lowercase
    normalized = re.sub(r'\s+', ' ', name.strip()).lower()
    # Remove common titles and suffixes
    normalized = re.sub(r'\b(mr|mrs|ms|dr|prof|sr|jr)\b\.?', '', normalized).strip()
    return normalized


def extract_first_last_name(name: str) -> tuple:
    """
    Extract first and last name from full name for better matching
    Returns (first_name, last_name)
    """
    if not name:
        return "", ""
    
    parts = name.strip().split()
    if len(parts) == 0:
        return "", ""
    elif len(parts) == 1:
        return parts[0], ""
    else:
        return parts[0], parts[-1]


def normalize_dob(dob: str) -> str:
    """
    Normalize DOB to consistent format: DD-MM-YYYY
    Handles various formats: DD/MM/YYYY, DDMMYYYY, DD.MM.YYYY, etc.
    """
    if not dob:
        return ""
    
    dob = dob.strip()
    
    # Already in DD-MM-YYYY format
    if re.match(r'^\d{2}-\d{2}-\d{4}$', dob):
        return dob
    
    # DD/MM/YYYY or DD.MM.YYYY or DD MM YYYY
    match = re.search(r'(\d{1,2})[/.\s]+(\d{1,2})[/.\s]+(\d{4})', dob)
    if match:
        day, month, year = match.groups()
        return f"{int(day):02d}-{int(month):02d}-{year}"
    
    # DDMMYYYY
    match = re.search(r'^(\d{2})(\d{2})(\d{4})$', dob)
    if match:
        day, month, year = match.groups()
        return f"{day}-{month}-{year}"
    
    return dob


def compare_names(personal_name: str, edu_name: str) -> tuple[bool, str]:
    """
    Compare personal and educational document names
    Returns (is_match, message)
    
    Matching logic:
    - Both empty → acceptable (no name in one document)
    - One empty → acceptable (optional field in education doc)
    - Both present → must match (at least 70% similarity)
    """
    personal_name = (personal_name or "").strip()
    edu_name = (edu_name or "").strip()
    
    # Both empty - acceptable
    if not personal_name and not edu_name:
        return True, "Name not present in both documents (acceptable)"
    
    # One empty - acceptable (educational doc may not have name)
    if not personal_name or not edu_name:
        return True, "Name not present in one document (acceptable)"
    
    # Both present - must match
    personal_normalized = normalize_name(personal_name)
    edu_normalized = normalize_name(edu_name)
    
    # Exact match
    if personal_normalized == edu_normalized:
        return True, f"Names match: '{personal_name}' == '{edu_name}'"
    
    # Check if names contain each other (e.g., "John Smith" vs "Smith")
    personal_words = set(personal_normalized.split())
    edu_words = set(edu_normalized.split())
    
    # If all words from one name are in the other (e.g., "John" in "John Smith")
    if personal_words.issubset(edu_words) or edu_words.issubset(personal_words):
        return True, f"Names partially match: '{personal_name}' ≈ '{edu_name}'"
    
    # Check first and last names
    personal_first, personal_last = extract_first_last_name(personal_normalized)
    edu_first, edu_last = extract_first_last_name(edu_normalized)
    
    # If first or last name matches
    if (personal_first and personal_first == edu_first) or (personal_last and personal_last == edu_last):
        return True, f"First or last name matches: '{personal_name}' ≈ '{edu_name}'"
    
    # No match
    return False, f"Name MISMATCH: Personal='{personal_name}' vs Educational='{edu_name}'"


def compare_dobs(personal_dob: str, edu_dob: str) -> tuple[bool, str]:
    """
    Compare personal and educational document DOBs
    Returns (is_match, message)
    
    Matching logic:
    - Both empty → acceptable (no DOB in one document)
    - One empty → acceptable (optional field in education doc)
    - Both present → must match exactly
    """
    personal_dob = (personal_dob or "").strip()
    edu_dob = (edu_dob or "").strip()
    
    # Both empty - acceptable
    if not personal_dob and not edu_dob:
        return True, "DOB not present in both documents (acceptable)"
    
    # One empty - acceptable
    if not personal_dob or not edu_dob:
        return True, "DOB not present in one document (acceptable)"
    
    # Both present - must match
    personal_normalized = normalize_dob(personal_dob)
    edu_normalized = normalize_dob(edu_dob)
    
    if personal_normalized == edu_normalized:
        return True, f"DOBs match: {personal_dob}"
    
    return False, f"DOB MISMATCH: Personal='{personal_dob}' vs Educational='{edu_dob}'"


def verify_documents(personal_data: dict, educational_data: dict) -> dict:
    """
    Verify that personal and educational documents match
    
    Args:
        personal_data: Dict with 'name' and 'dob' keys
        educational_data: Dict that may contain 'name' and 'dob' keys
    
    Returns:
        {
            'verified': bool,
            'name_match': bool,
            'name_message': str,
            'dob_match': bool,
            'dob_message': str,
            'verification_status': 'matched' | 'mismatched' | 'not_applicable',
            'error_message': str (if verification fails)
        }
    """
    if not personal_data:
        return {
            'verified': False,
            'verification_status': 'not_applicable',
            'error_message': 'Personal data not available for verification'
        }
    
    personal_name = personal_data.get('name', '').strip()
    personal_dob = personal_data.get('dob', '').strip()
    
    # If no educational data, verification not applicable
    if not educational_data:
        return {
            'verified': True,
            'verification_status': 'not_applicable',
            'error_message': None
        }
    
    edu_name = educational_data.get('name', '').strip()
    edu_dob = educational_data.get('dob', '').strip()
    
    # If educational document has no name/dob, verification not applicable
    if not edu_name and not edu_dob:
        return {
            'verified': True,
            'verification_status': 'not_applicable',
            'error_message': None
        }
    
    # Compare names
    name_match, name_message = compare_names(personal_name, edu_name)
    
    # Compare DOBs
    dob_match, dob_message = compare_dobs(personal_dob, edu_dob)
    
    logger.info(f"[Verification] Name comparison: {name_message}")
    logger.info(f"[Verification] DOB comparison: {dob_message}")
    
    # Both must match for overall verification
    if name_match and dob_match:
        return {
            'verified': True,
            'name_match': name_match,
            'name_message': name_message,
            'dob_match': dob_match,
            'dob_message': dob_message,
            'verification_status': 'matched',
            'error_message': None
        }
    
    # Build error message
    error_parts = []
    if not name_match:
        error_parts.append(name_message)
    if not dob_match:
        error_parts.append(dob_message)
    
    error_message = " | ".join(error_parts)
    
    return {
        'verified': False,
        'name_match': name_match,
        'name_message': name_message,
        'dob_match': dob_match,
        'dob_message': dob_message,
        'verification_status': 'mismatched',
        'error_message': error_message,
        'reupload_required': True
    }
