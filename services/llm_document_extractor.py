import json
import logging
from typing import Dict, Optional
import re

logger = logging.getLogger(__name__)

# Try to import OpenAI client
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI client not available")


def _call_llm(prompt: str, model: str = "gpt-4-turbo", temperature: float = 0.3) -> Optional[str]:
    """
    Call OpenAI LLM with prompt
    Returns: raw response text or None on failure
    """
    if not OPENAI_AVAILABLE:
        logger.error("OpenAI client not available")
        return None
    
    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert document extraction assistant. Extract information precisely from OCR text."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=temperature,
            max_tokens=1000
        )
        
        result_text = response.choices[0].message.content
        logger.info(f"LLM response received: {len(result_text)} characters")
        return result_text
    except Exception as e:
        logger.error(f"LLM API error: {str(e)}", exc_info=True)
        return None


def _parse_json_response(response_text: str) -> Optional[Dict]:
    """
    Parse JSON from LLM response
    Handles cases where JSON is embedded in markdown code blocks
    """
    try:
        if not response_text:
            logger.warning("Empty response text")
            return None
        
        # Try to extract JSON from markdown code blocks
        if "```json" in response_text:
            match = re.search(r'```json\s*\n(.*?)\n```', response_text, re.DOTALL)
            if match:
                json_str = match.group(1)
                logger.debug(f"Extracted JSON from markdown code block")
            else:
                json_str = response_text
        elif "```" in response_text:
            match = re.search(r'```\s*\n(.*?)\n```', response_text, re.DOTALL)
            if match:
                json_str = match.group(1)
                logger.debug(f"Extracted JSON from code block")
            else:
                json_str = response_text
        else:
            json_str = response_text
        
        # Parse JSON
        data = json.loads(json_str.strip())
        logger.info(f"Successfully parsed JSON response: {list(data.keys())}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {str(e)}")
        logger.debug(f"Response text: {response_text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Error parsing LLM response: {str(e)}", exc_info=True)
        return None


def extract_personal_data(raw_text: str) -> Optional[Dict]:
    """
    Extract personal data (name, DOB, address) from OCR text
    Returns: {name, date_of_birth, address} or None on failure
    """
    if not raw_text or len(raw_text.strip()) < 50:
        logger.error("Insufficient text for extraction")
        return None
    
    prompt = f"""Extract personal information from the OCR text below.
Return ONLY valid JSON matching this schema exactly:

{{
  "name": "full name from document",
  "date_of_birth": "format as YYYY-MM-DD",
  "address": "complete address from document"
}}

Rules:
- If a field is not clearly found, use null
- For date_of_birth, convert to YYYY-MM-DD format
- Return ONLY JSON, no other text

OCR Text:
{raw_text}"""
    
    logger.info("Calling LLM for personal data extraction")
    response = _call_llm(prompt)
    if not response:
        logger.error("LLM extraction failed")
        return None
    
    data = _parse_json_response(response)
    if not data:
        logger.error("Failed to parse JSON response")
        return None
    
    # Validate required fields exist
    if not all(key in data for key in ["name", "date_of_birth", "address"]):
        logger.warning(f"Missing required fields in response: {list(data.keys())}")
    
    logger.info(f"Successfully extracted personal data: {data.get('name', 'UNKNOWN')}")
    return data


def extract_10th_data(raw_text: str) -> Optional[Dict]:
    """
    Extract 10th marksheet data from OCR text
    Returns: 8-field dictionary or None on failure
    """
    if not raw_text or len(raw_text.strip()) < 50:
        logger.error("Insufficient text for extraction")
        return None
    
    prompt = f"""Extract Class 10 marksheet information from the OCR text below.
Return ONLY valid JSON matching this schema exactly:

{{
  "document_type": "e.g., 'marksheet' or 'certificate'",
  "qualification": "Class 10",
  "board": "e.g., 'CBSE', 'State Board', etc",
  "stream": "e.g., 'Science', 'Commerce', 'Arts', or 'General'",
  "year_of_passing": "e.g., '2017' or '2015-2016'",
  "school_name": "full school name",
  "marks_type": "either 'Percentage', 'CGPA', or 'Marks'",
  "marks": "as appears on document (e.g., '87.5%' or '8.2 CGPA' or '420/500')"
}}

Rules:
- If a field is not found, use null
- Extract exactly as shown in the document
- Return ONLY JSON, no other text

OCR Text:
{raw_text}"""
    
    logger.info("Calling LLM for 10th marksheet extraction")
    response = _call_llm(prompt)
    if not response:
        logger.error("LLM extraction failed")
        return None
    
    data = _parse_json_response(response)
    if not data:
        logger.error("Failed to parse JSON response")
        return None
    
    # Validate required fields
    required_fields = ["document_type", "qualification", "board", "stream", 
                       "year_of_passing", "school_name", "marks_type", "marks"]
    if not all(key in data for key in required_fields):
        logger.warning(f"Missing required fields: {[f for f in required_fields if f not in data]}")
    
    logger.info(f"Successfully extracted 10th data: Board={data.get('board')}, Marks={data.get('marks')}")
    return data


def extract_12th_data(raw_text: str) -> Optional[Dict]:
    """
    Extract 12th marksheet data from OCR text
    Returns: 8-field dictionary or None on failure
    """
    if not raw_text or len(raw_text.strip()) < 50:
        logger.error("Insufficient text for extraction")
        return None
    
    prompt = f"""Extract Class 12 marksheet information from the OCR text below.
Return ONLY valid JSON matching this schema exactly:

{{
  "document_type": "e.g., 'marksheet' or 'certificate'",
  "qualification": "Class 12",
  "board": "e.g., 'CBSE', 'State Board', etc",
  "stream": "e.g., 'Science', 'Commerce', 'Arts'",
  "year_of_passing": "e.g., '2019' or '2018-2019'",
  "school_name": "full school name",
  "marks_type": "either 'Percentage', 'CGPA', or 'Marks'",
  "marks": "as appears on document (e.g., '92.5%' or '9.2 CGPA' or '465/500')"
}}

Rules:
- If a field is not found, use null
- Extract exactly as shown in the document
- Return ONLY JSON, no other text

OCR Text:
{raw_text}"""
    
    logger.info("Calling LLM for 12th marksheet extraction")
    response = _call_llm(prompt)
    if not response:
        logger.error("LLM extraction failed")
        return None
    
    data = _parse_json_response(response)
    if not data:
        logger.error("Failed to parse JSON response")
        return None
    
    # Validate required fields
    required_fields = ["document_type", "qualification", "board", "stream", 
                       "year_of_passing", "school_name", "marks_type", "marks"]
    if not all(key in data for key in required_fields):
        logger.warning(f"Missing required fields: {[f for f in required_fields if f not in data]}")
    
    logger.info(f"Successfully extracted 12th data: Board={data.get('board')}, Marks={data.get('marks')}")
    return data
