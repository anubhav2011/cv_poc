"""
Enhanced document upload and verification endpoints
These endpoints integrate document_processor, ocr_service, llm_document_extractor, and document_verifier services
"""

import logging
import asyncio
from fastapi import UploadFile, Form, HTTPException, APIRouter
from fastapi.responses import JSONResponse
import uuid
import os
from pathlib import Path

from ..db import crud
from ..config import PERSONAL_DOCUMENTS_DIR, EDUCATIONAL_DOCUMENTS_DIR
from ..services.document_processor import (
    validate_document_format, is_camera_capture, convert_camera_to_image,
    save_uploaded_file, save_pil_image_to_file, get_document_type
)
from ..services.ocr_service import ocr_to_text
from ..services.llm_document_extractor import (
    extract_personal_data, extract_10th_data, extract_12th_data
)
from ..services.document_verifier import verify_worker_documents, extract_verification_errors

logger = logging.getLogger(__name__)

# Create sub-router for enhanced endpoints
enhanced_router = APIRouter(prefix="/form", tags=["form-enhanced"])


def _build_response(status_code: int, success: bool, message: str, data: dict = None, error_code: str = None):
    """Build standardized API response"""
    response = {
        "statusCode": status_code,
        "responseData": {
            "message": message
        }
    }
    if error_code:
        response["responseData"]["error_code"] = error_code
    if data:
        response["responseData"].update(data)
    return JSONResponse(status_code=status_code, content=response)


@enhanced_router.post("/personal/upload")
async def upload_personal_document(
    worker_id: str = Form(...),
    document_file: UploadFile = None,
    camera_data: str = Form(None)
):
    """
    Upload and process personal document (identity document)
    Extracts: name, date_of_birth, address
    
    Supports: PDF, JPG, PNG, or Base64 camera capture
    """
    try:
        # Validate input
        if not worker_id:
            return _build_response(400, False, "worker_id is required", 
                                  error_code="MISSING_WORKER_ID")
        
        if not document_file and not camera_data:
            return _build_response(400, False, "Either document_file or camera_data required",
                                  error_code="MISSING_FILE")
        
        logger.info(f"[PERSONAL UPLOAD] Processing personal document for worker {worker_id}")
        
        # Verify worker exists
        worker = crud.get_worker(worker_id)
        if not worker:
            return _build_response(404, False, "Worker not found",
                                  error_code="WORKER_NOT_FOUND")
        
        file_path = None
        
        # Handle camera capture
        if camera_data:
            logger.info(f"[PERSONAL UPLOAD] Processing camera capture for {worker_id}")
            image, error = convert_camera_to_image(camera_data)
            if error:
                logger.error(f"[PERSONAL UPLOAD] Camera conversion failed: {error}")
                return _build_response(400, False, error, error_code="CAMERA_CONVERSION_FAILED")
            
            file_path, error = save_pil_image_to_file(image, worker_id, "personal", PERSONAL_DOCUMENTS_DIR)
            if error:
                logger.error(f"[PERSONAL UPLOAD] Failed to save camera image: {error}")
                return _build_response(500, False, error, error_code="FILE_SAVE_FAILED")
        
        # Handle file upload
        elif document_file:
            logger.info(f"[PERSONAL UPLOAD] Processing file upload: {document_file.filename}")
            
            if not validate_document_format(document_file.filename):
                return _build_response(400, False, "Invalid file format. Allowed: PDF, JPG, PNG",
                                      error_code="INVALID_FILE_FORMAT")
            
            content = await document_file.read()
            file_path, error = save_uploaded_file(content, document_file.filename, worker_id, 
                                                 "personal", PERSONAL_DOCUMENTS_DIR)
            if error:
                logger.error(f"[PERSONAL UPLOAD] File save failed: {error}")
                return _build_response(500, False, error, error_code="FILE_SAVE_FAILED")
        
        logger.info(f"[PERSONAL UPLOAD] File saved: {file_path}")
        
        # Extract OCR text (complete document)
        logger.info(f"[PERSONAL UPLOAD] Starting OCR extraction...")
        raw_ocr_text = ocr_to_text(file_path)
        
        if not raw_ocr_text or len(raw_ocr_text.strip()) < 50:
            logger.error(f"[PERSONAL UPLOAD] OCR extraction failed - insufficient text")
            crud.save_document_extraction(worker_id, "personal", raw_ocr_text or "", {}, file_path, 
                                         "failed", "OCR extraction failed or returned insufficient text")
            return _build_response(400, False, "Failed to extract text from document. Please upload a clearer image.",
                                  error_code="OCR_EXTRACTION_FAILED")
        
        logger.info(f"[PERSONAL UPLOAD] OCR extraction successful: {len(raw_ocr_text)} characters")
        
        # Extract structured data via LLM
        logger.info(f"[PERSONAL UPLOAD] Extracting structured data via LLM...")
        extracted_data = extract_personal_data(raw_ocr_text)
        
        if not extracted_data:
            logger.error(f"[PERSONAL UPLOAD] LLM extraction failed")
            crud.save_document_extraction(worker_id, "personal", raw_ocr_text, {}, file_path,
                                         "failed", "LLM extraction failed")
            return _build_response(400, False, "Failed to extract personal data. Please try again.",
                                  error_code="LLM_EXTRACTION_FAILED")
        
        logger.info(f"[PERSONAL UPLOAD] Extracted: {extracted_data.get('name', 'UNKNOWN')}")
        
        # Save to database
        logger.info(f"[PERSONAL UPLOAD] Saving to database...")
        name = extracted_data.get("name") or ""
        dob = extracted_data.get("date_of_birth") or ""
        address = extracted_data.get("address") or ""
        
        # Update worker with extracted data
        success = crud.update_worker_data(worker_id, name, dob, address)
        
        if not success:
            logger.error(f"[PERSONAL UPLOAD] Database update failed")
            return _build_response(500, False, "Failed to save extracted data",
                                  error_code="DATABASE_SAVE_FAILED")
        
        # Save to extraction log
        crud.save_document_extraction(worker_id, "personal", raw_ocr_text, extracted_data, file_path)
        
        logger.info(f"[PERSONAL UPLOAD] ✓ Completed successfully for {worker_id}")
        
        return _build_response(200, True, "Personal document processed successfully",
                              {"worker_id": worker_id, "extracted_data": extracted_data})
        
    except Exception as e:
        logger.error(f"[PERSONAL UPLOAD] Exception: {str(e)}", exc_info=True)
        return _build_response(500, False, f"Internal server error: {str(e)}",
                              error_code="INTERNAL_ERROR")


@enhanced_router.post("/educational/upload")
async def upload_educational_documents(
    worker_id: str = Form(...),
    file_10th: UploadFile = None,
    file_12th: UploadFile = None,
    camera_data_10th: str = Form(None),
    camera_data_12th: str = Form(None)
):
    """
    Upload and process 10th and/or 12th marksheets
    Extracts: document_type, qualification, board, stream, year_of_passing, school_name, marks_type, marks
    
    At least one of (file_10th, camera_data_10th) or (file_12th, camera_data_12th) required
    """
    try:
        if not worker_id:
            return _build_response(400, False, "worker_id is required",
                                  error_code="MISSING_WORKER_ID")
        
        # Verify worker exists
        worker = crud.get_worker(worker_id)
        if not worker:
            return _build_response(404, False, "Worker not found",
                                  error_code="WORKER_NOT_FOUND")
        
        if not file_10th and not camera_data_10th and not file_12th and not camera_data_12th:
            return _build_response(400, False, "At least one document (10th or 12th) is required",
                                  error_code="MISSING_DOCUMENTS")
        
        logger.info(f"[EDUCATION UPLOAD] Processing educational documents for {worker_id}")
        
        results = []
        
        # Process 10th document
        if file_10th or camera_data_10th:
            logger.info(f"[EDUCATION UPLOAD] Processing 10th document...")
            file_path_10th, extracted_10th = await _process_educational_document(
                worker_id, "10th", file_10th, camera_data_10th, extract_10th_data
            )
            
            if extracted_10th is None:
                return _build_response(400, False, "Failed to process 10th document",
                                      error_code="10TH_PROCESSING_FAILED")
            
            # Save to database
            success = crud.update_educational_document_extraction(worker_id, "10th", extracted_10th, 
                                                                 extracted_10th.get("_raw_ocr", ""), 
                                                                 file_path_10th or "")
            if success:
                results.append({"class": "10th", **extracted_10th})
                logger.info(f"[EDUCATION UPLOAD] ✓ 10th document processed")
        
        # Process 12th document
        if file_12th or camera_data_12th:
            logger.info(f"[EDUCATION UPLOAD] Processing 12th document...")
            file_path_12th, extracted_12th = await _process_educational_document(
                worker_id, "12th", file_12th, camera_data_12th, extract_12th_data
            )
            
            if extracted_12th is None:
                return _build_response(400, False, "Failed to process 12th document",
                                      error_code="12TH_PROCESSING_FAILED")
            
            # Save to database
            success = crud.update_educational_document_extraction(worker_id, "12th", extracted_12th,
                                                                 extracted_12th.get("_raw_ocr", ""),
                                                                 file_path_12th or "")
            if success:
                results.append({"class": "12th", **extracted_12th})
                logger.info(f"[EDUCATION UPLOAD] ✓ 12th document processed")
        
        if not results:
            return _build_response(400, False, "No documents were successfully processed",
                                  error_code="ALL_PROCESSING_FAILED")
        
        logger.info(f"[EDUCATION UPLOAD] ✓ Completed successfully for {worker_id}")
        
        return _build_response(200, True, "Educational documents processed successfully",
                              {"worker_id": worker_id, "documents": results})
        
    except Exception as e:
        logger.error(f"[EDUCATION UPLOAD] Exception: {str(e)}", exc_info=True)
        return _build_response(500, False, f"Internal server error: {str(e)}",
                              error_code="INTERNAL_ERROR")


async def _process_educational_document(worker_id: str, class_level: str, file_upload, 
                                       camera_data, extractor_func):
    """
    Helper to process a single educational document
    Returns: (file_path, extracted_data or None)
    """
    try:
        file_path = None
        raw_ocr_text = None
        
        # Handle camera capture
        if camera_data:
            image, error = convert_camera_to_image(camera_data)
            if error:
                logger.error(f"[EDUCATION] Camera conversion failed for {class_level}: {error}")
                return None, None
            
            file_path, error = save_pil_image_to_file(image, worker_id, f"education_{class_level}", 
                                                     EDUCATIONAL_DOCUMENTS_DIR)
            if error:
                logger.error(f"[EDUCATION] File save failed for {class_level}: {error}")
                return None, None
        
        # Handle file upload
        elif file_upload:
            if not validate_document_format(file_upload.filename):
                logger.error(f"[EDUCATION] Invalid file format: {file_upload.filename}")
                return None, None
            
            content = await file_upload.read()
            file_path, error = save_uploaded_file(content, file_upload.filename, worker_id,
                                                 f"education_{class_level}", EDUCATIONAL_DOCUMENTS_DIR)
            if error:
                logger.error(f"[EDUCATION] File save failed: {error}")
                return None, None
        
        # Extract OCR
        logger.info(f"[EDUCATION] Extracting OCR for {class_level}...")
        raw_ocr_text = ocr_to_text(file_path)
        
        if not raw_ocr_text or len(raw_ocr_text.strip()) < 50:
            logger.error(f"[EDUCATION] OCR extraction failed for {class_level}")
            crud.save_document_extraction(worker_id, class_level, raw_ocr_text or "", {}, file_path,
                                         "failed", "OCR extraction failed")
            return file_path, None
        
        logger.info(f"[EDUCATION] OCR successful for {class_level}: {len(raw_ocr_text)} chars")
        
        # Extract structured data
        logger.info(f"[EDUCATION] Extracting data via LLM for {class_level}...")
        extracted_data = extractor_func(raw_ocr_text)
        
        if not extracted_data:
            logger.error(f"[EDUCATION] LLM extraction failed for {class_level}")
            crud.save_document_extraction(worker_id, class_level, raw_ocr_text, {}, file_path,
                                         "failed", "LLM extraction failed")
            return file_path, None
        
        # Store raw OCR for later (will be removed before returning to client)
        extracted_data["_raw_ocr"] = raw_ocr_text
        
        # Save to extraction log
        extracted_data_clean = {k: v for k, v in extracted_data.items() if k != "_raw_ocr"}
        crud.save_document_extraction(worker_id, class_level, raw_ocr_text, extracted_data_clean,
                                     file_path)
        
        logger.info(f"[EDUCATION] ✓ Extracted {class_level} document")
        return file_path, extracted_data_clean
        
    except Exception as e:
        logger.error(f"[EDUCATION] Exception processing {class_level}: {str(e)}", exc_info=True)
        return None, None


@enhanced_router.get("/worker/{worker_id}/verify")
async def verify_worker_documents_endpoint(worker_id: str):
    """
    Verify consistency across worker's documents (personal, 10th, 12th)
    Compares: name (fuzzy match 85%+), DOB (exact match)
    
    Returns: verification status and detailed comparison results
    """
    try:
        if not worker_id:
            return _build_response(400, False, "worker_id is required",
                                  error_code="MISSING_WORKER_ID")
        
        logger.info(f"[VERIFICATION] Starting verification for {worker_id}")
        
        # Get all document data
        personal = crud.get_worker(worker_id)
        edu_10th = crud.get_educational_document(worker_id, "10th")
        edu_12th = crud.get_educational_document(worker_id, "12th")
        
        if not personal:
            return _build_response(404, False, "Worker not found",
                                  error_code="WORKER_NOT_FOUND")
        
        # Perform verification
        verification_result = verify_worker_documents(personal, edu_10th, edu_12th, name_threshold=0.85)
        
        # Update worker verification status
        verification_errors = extract_verification_errors(verification_result)
        crud.update_worker_verification_status(worker_id, verification_result["overall_status"],
                                              verification_errors)
        
        # Log verification
        for comp in verification_result.get("comparisons", []):
            crud.save_verification_log(worker_id, comp["type"], comp["details"],
                                      comp["status"])
        
        # Build response based on status
        if verification_result["overall_status"] == "verified":
            logger.info(f"[VERIFICATION] ✓ Worker {worker_id} verified successfully")
            return _build_response(200, True, "All documents verified successfully",
                                  {"verification_status": "verified",
                                   "comparisons": verification_result["comparisons"]})
        
        elif verification_result["overall_status"] == "failed":
            logger.error(f"[VERIFICATION] ✗ Verification failed for {worker_id}")
            return _build_response(400, False, "Document verification failed - see details",
                                  {"verification_status": "failed",
                                   "errors": [c.get("details", {}).get("issues", []) 
                                            for c in verification_result.get("comparisons", [])
                                            if c.get("status") == "failed"],
                                   "comparisons": verification_result["comparisons"]},
                                  error_code="VERIFICATION_FAILED")
        
        else:  # incomplete
            logger.warning(f"[VERIFICATION] Incomplete data for {worker_id}")
            return _build_response(206, False, "Incomplete verification - missing documents",
                                  {"verification_status": "incomplete",
                                   "message": verification_result.get("errors", ["Unknown error"])},
                                  error_code="INCOMPLETE_DATA")
        
    except Exception as e:
        logger.error(f"[VERIFICATION] Exception: {str(e)}", exc_info=True)
        return _build_response(500, False, f"Internal server error: {str(e)}",
                              error_code="INTERNAL_ERROR")
