import json
import os
import logging
from typing import Optional

# Get logger (logging configured in main)
logger = logging.getLogger(__name__)

# Initialize OpenAI client (lazy loading)
openai_client = None


def get_openai_client():
    """Get or initialize OpenAI client (lazy loading with error handling)"""
    global openai_client
    if openai_client is None:
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY not set. LLM extraction will be skipped.")
                return None
            from openai import OpenAI
            openai_client = OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized successfully for LLM extraction")
        except ImportError:
            logger.warning("OpenAI library not installed. Install with: pip install openai")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            return None
    return openai_client


async def extract_personal_data_from_ocr(ocr_text: str) -> Optional[dict]:
    """
    Extract personal data (name, dob, address) from OCR text using LLM.
    Uses OpenAI API to parse structured data from raw OCR text.
    
    Args:
        ocr_text: Raw OCR extracted text from personal document
        
    Returns:
        dict with keys: name, dob, address (or None on extraction failure)
    """
    if not ocr_text or len(ocr_text.strip()) < 10:
        logger.warning("[LLM Extractor] Personal OCR text too short for extraction")
        return None
    
    client = get_openai_client()
    if not client:
        logger.warning("[LLM Extractor] OpenAI client not available, skipping LLM extraction")
        return None
    
    prompt = """You are a document data extraction assistant.
Extract the following information from the provided OCR text of a personal document (Aadhaar, Passport, ID, Driving License, etc.):
1. Name: Full name of the person
2. Date of Birth: In format DD-MM-YYYY
3. Address: Complete address

Return ONLY valid JSON (no markdown, no code blocks, no extra text):
{
  "name": "string or null",
  "dob": "string (DD-MM-YYYY) or null",
  "address": "string or null"
}

If any field cannot be extracted, use null value.
Ensure valid JSON format.

OCR TEXT:
{ocr_text}"""
    
    try:
        logger.info("[LLM Extractor] Sending personal OCR text to LLM for extraction...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise document data extraction assistant. Extract only the requested fields. Return valid JSON only."
                },
                {
                    "role": "user",
                    "content": prompt.format(ocr_text=ocr_text)
                }
            ],
            temperature=0.1,  # Low temperature for consistent extraction
            max_tokens=500
        )
        
        llm_response = response.choices[0].message.content.strip()
        logger.info("[LLM Extractor] LLM response received, parsing JSON...")
        
        # Parse JSON response
        try:
            extracted_data = json.loads(llm_response)
            logger.info(f"[LLM Extractor] ✓ Successfully extracted personal data: name={bool(extracted_data.get('name'))}, dob={bool(extracted_data.get('dob'))}, address={bool(extracted_data.get('address'))}")
            
            # Ensure all fields exist with proper None values
            return {
                "name": extracted_data.get("name"),
                "dob": extracted_data.get("dob"),
                "address": extracted_data.get("address")
            }
        except json.JSONDecodeError as json_error:
            logger.error(f"[LLM Extractor] Failed to parse LLM JSON response: {llm_response[:200]}")
            logger.error(f"[LLM Extractor] JSON parse error: {str(json_error)}")
            return None
            
    except Exception as e:
        logger.error(f"[LLM Extractor] Error in LLM extraction: {str(e)}", exc_info=True)
        return None


async def extract_educational_data_from_ocr(ocr_text: str) -> Optional[dict]:
    """
    Extract educational data from OCR text using LLM.
    Extracts: document_type, qualification, board, stream, year_of_passing, school_name, marks_type, marks
    
    Args:
        ocr_text: Raw OCR extracted text from educational document
        
    Returns:
        dict with all 8 educational fields (or None on extraction failure)
    """
    if not ocr_text or len(ocr_text.strip()) < 10:
        logger.warning("[LLM Extractor] Educational OCR text too short for extraction")
        return None
    
    client = get_openai_client()
    if not client:
        logger.warning("[LLM Extractor] OpenAI client not available, skipping LLM extraction")
        return None
    
    prompt = """You are an educational document data extraction assistant.
Extract the following information from the provided OCR text of an educational document (marksheet, certificate, transcript, report card, etc.):
1. document_type: Type (e.g., "marksheet", "certificate", "transcript", "report card")
2. qualification: Class/Degree level (e.g., "Class 10", "10th", "SSC", "Bachelor of Science")
3. board: Board/University name (e.g., "CBSE", "ICSE", "State Board", "Delhi University")
4. stream: Stream/specialization (e.g., "Science", "Commerce", "Arts", "Science with Mathematics")
5. year_of_passing: Year of exam (YYYY format, e.g., "2020")
6. school_name: Name of school/institution
7. marks_type: Type of marks (e.g., "Percentage", "CGPA", "Grade", "Marks out of 100")
8. marks: Actual marks/CGPA/grade (e.g., "85%", "9.2 CGPA", "A+")

Return ONLY valid JSON (no markdown, no code blocks, no extra text):
{
  "document_type": "string or null",
  "qualification": "string or null",
  "board": "string or null",
  "stream": "string or null",
  "year_of_passing": "string or null",
  "school_name": "string or null",
  "marks_type": "string or null",
  "marks": "string or null"
}

If any field cannot be extracted, use null value.
Ensure valid JSON format.

OCR TEXT:
{ocr_text}"""
    
    try:
        logger.info("[LLM Extractor] Sending educational OCR text to LLM for extraction...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise document data extraction assistant. Extract only the requested fields. Return valid JSON only."
                },
                {
                    "role": "user",
                    "content": prompt.format(ocr_text=ocr_text)
                }
            ],
            temperature=0.1,  # Low temperature for consistent extraction
            max_tokens=500
        )
        
        llm_response = response.choices[0].message.content.strip()
        logger.info("[LLM Extractor] LLM response received, parsing JSON...")
        
        # Parse JSON response
        try:
            extracted_data = json.loads(llm_response)
            logger.info(f"[LLM Extractor] ✓ Successfully extracted educational data: qualification={bool(extracted_data.get('qualification'))}, board={bool(extracted_data.get('board'))}, marks={bool(extracted_data.get('marks'))}")
            
            # Ensure all 8 fields exist with proper None values
            return {
                "document_type": extracted_data.get("document_type"),
                "qualification": extracted_data.get("qualification"),
                "board": extracted_data.get("board"),
                "stream": extracted_data.get("stream"),
                "year_of_passing": extracted_data.get("year_of_passing"),
                "school_name": extracted_data.get("school_name"),
                "marks_type": extracted_data.get("marks_type"),
                "marks": extracted_data.get("marks")
            }
        except json.JSONDecodeError as json_error:
            logger.error(f"[LLM Extractor] Failed to parse LLM JSON response: {llm_response[:200]}")
            logger.error(f"[LLM Extractor] JSON parse error: {str(json_error)}")
            return None
            
    except Exception as e:
        logger.error(f"[LLM Extractor] Error in LLM extraction: {str(e)}", exc_info=True)
        return None
