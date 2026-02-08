# Document Extraction & Verification Architecture

## Overview
This system implements end-to-end document processing with multi-strategy OCR extraction, LLM-based structured data extraction, and cross-document verification for CV/resume building.

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT REQUEST                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                          (PDF/JPG/PNG/Camera Base64)                             │
└──────────────────────────┬──────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
        ▼                                     ▼
   ┌─────────────────┐              ┌──────────────────┐
   │ Personal Upload │              │ Education Upload │
   │  Endpoint       │              │  Endpoint        │
   │ (POST/personal) │              │ (POST/education) │
   └────────┬────────┘              └────────┬─────────┘
        │                                    │
        └────────────────┬───────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────────┐
        │   Document Processor Service        │
        ├─────────────────────────────────────┤
        │ • Validate format (PDF/JPG/PNG)     │
        │ • Handle camera captures (base64)   │
        │ • Convert to PIL Image              │
        │ • Save to disk                      │
        └─────────────────┬───────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────────────────────────────┐
        │              OCR EXTRACTION - Multi-Strategy Fallback       │
        ├─────────────────────────────────────────────────────────────┤
        │                                                               │
        │  Strategy 1: Native PDF Text (pdfplumber)                   │
        │  ├─ Extract text directly from PDF                          │
        │  ├─ If success & text > 100 chars → RETURN text             │
        │  └─ Else → Try Strategy 2                                    │
        │                                                               │
        │  Strategy 2: PDF → Images + PaddleOCR                       │
        │  ├─ Convert PDF to images (300 DPI)                         │
        │  ├─ Run PaddleOCR on each page                              │
        │  ├─ Combine text from all pages                             │
        │  ├─ If success & text > 50 chars → RETURN text              │
        │  └─ Else → Try Strategy 3                                    │
        │                                                               │
        │  Strategy 3: PDF → Images + Tesseract                       │
        │  ├─ Same as Strategy 2 but use Tesseract OCR                │
        │  ├─ If success & text > 50 chars → RETURN text              │
        │  └─ Else → Try Strategy 4                                    │
        │                                                               │
        │  Strategy 4: Direct Image OCR                               │
        │  ├─ For JPG/PNG files                                       │
        │  ├─ Try PaddleOCR first                                     │
        │  ├─ Fallback to Tesseract                                   │
        │  └─ If failure → ERROR 400 (OCR_EXTRACTION_FAILED)          │
        │                                                               │
        └──────────────────────────┬──────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼                             ▼
        ┌─────────────────────────┐  ┌──────────────────────────┐
        │  Complete Raw OCR Text  │  │  Quality Validation      │
        │  (All pages/content)    │  │  (Min 50 chars check)    │
        └──────────┬──────────────┘  └──────────────────────────┘
                   │
                   ▼
        ┌─────────────────────────────────────────────────────────────┐
        │         LLM Document Extractor Service                      │
        ├─────────────────────────────────────────────────────────────┤
        │                                                               │
        │  Input: Complete raw OCR text + JSON Schema                 │
        │                                                               │
        │  Personal Document Extraction:                              │
        │  ├─ LLM Prompt with JSON schema for 3 fields:               │
        │  │  {name, date_of_birth, address}                          │
        │  ├─ Parse JSON response from LLM                            │
        │  └─ Return structured data with null for missing fields     │
        │                                                               │
        │  Educational Document Extraction (10th/12th):              │
        │  ├─ LLM Prompt with JSON schema for 8 fields:               │
        │  │  {document_type, qualification, board, stream,           │
        │  │   year_of_passing, school_name, marks_type, marks}       │
        │  ├─ Parse JSON response from LLM                            │
        │  └─ Return structured data with null for missing fields     │
        │                                                               │
        │  LLM Configuration:                                         │
        │  • Model: GPT-4                                             │
        │  • Temperature: 0.3 (consistent output)                     │
        │  • Timeout: 30 seconds                                      │
        │                                                               │
        └──────────────────────────┬───────────────────────────────────┘
                                   │
                                   ▼
        ┌─────────────────────────────────────────────────────────────┐
        │            Database Operations (CRUD)                       │
        ├─────────────────────────────────────────────────────────────┤
        │                                                               │
        │  Save to DB:                                                │
        │  1. Update workers table with personal data                 │
        │  2. Save/Update educational_documents for 10th/12th         │
        │  3. Log extraction in document_extraction_log               │
        │                                                               │
        │  Fields stored:                                             │
        │  • raw_ocr_text (complete document text)                    │
        │  • extracted_data (JSON with structured fields)             │
        │  • file_path (location on disk)                             │
        │  • extraction_status ('success' or 'failed')                │
        │                                                               │
        └──────────────────────────┬───────────────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  Return 200 Response         │
                    │  With extracted data         │
                    └──────────────────────────────┘


        ┌─────────────────────────────────────────────────────────────┐
        │    Verification Flow (GET /form/worker/{id}/verify)         │
        ├─────────────────────────────────────────────────────────────┤
        │                                                               │
        │  1. Retrieve all document data from DB                       │
        │     ├─ Personal (name, DOB, address)                        │
        │     ├─ 10th document data                                   │
        │     └─ 12th document data                                   │
        │                                                               │
        │  2. Perform Cross-Document Comparisons:                      │
        │     ├─ Personal vs 10th                                     │
        │     ├─ Personal vs 12th                                     │
        │     └─ 10th vs 12th                                         │
        │                                                               │
        │  3. For Each Comparison:                                     │
        │     ├─ Name Matching:                                        │
        │     │  • Use Levenshtein distance                           │
        │     │  • Threshold: 85% similarity                          │
        │     │  • Status: 'matched' or 'mismatch'                    │
        │     │                                                        │
        │     └─ DOB Matching:                                         │
        │        • Exact match required (YYYY-MM-DD format)            │
        │        • Status: 'exact_match' or 'mismatch'                │
        │                                                               │
        │  4. Overall Result:                                          │
        │     ├─ All pass → verification_status = 'verified' (200)    │
        │     ├─ Any fail → verification_status = 'failed' (400)      │
        │     └─ Incomplete → verification_status = 'incomplete' (206)│
        │                                                               │
        │  5. Log verification to document_verification_log           │
        │                                                               │
        └──────────────────────────┬───────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
         (Verified) ▼                             ▼ (Failed/Incomplete)
        ┌─────────────────────────┐  ┌──────────────────────────┐
        │  Return 200/206/400     │  │  Include Error Details   │
        │  With verification      │  │  In response             │
        │  status & comparisons   │  └──────────────────────────┘
        └─────────────────────────┘
```

---

## API Endpoints

### 1. POST /form/personal/upload
**Purpose:** Upload and extract personal document (identity document)

**Request:**
```
Content-Type: multipart/form-data
- worker_id (string, required) - Worker ID
- document_file (file, optional) - PDF/JPG/PNG file
- camera_data (string, optional) - Base64 encoded camera capture
```

**Response (200 - Success):**
```json
{
  "statusCode": 200,
  "responseData": {
    "message": "Personal document processed successfully",
    "worker_id": "123",
    "extracted_data": {
      "name": "JOHN KUMAR SINGH",
      "date_of_birth": "1990-01-15",
      "address": "Plot No. 123, Main Road, Delhi 110001"
    }
  }
}
```

**Response (400 - Error):**
```json
{
  "statusCode": 400,
  "responseData": {
    "message": "Failed to extract text from document",
    "error_code": "OCR_EXTRACTION_FAILED"
  }
}
```

**Processing Flow:**
1. Validate file format (PDF/JPG/PNG)
2. Convert camera if needed
3. Save file to /uploads/personal/{worker_id}/
4. Extract complete OCR text (all pages/content)
5. LLM extraction using JSON schema (3 fields)
6. Save to DB and extraction log
7. Return extracted data

---

### 2. POST /form/educational/upload
**Purpose:** Upload and extract 10th and/or 12th marksheets

**Request:**
```
Content-Type: multipart/form-data
- worker_id (string, required) - Worker ID
- file_10th (file, optional) - 10th marksheet
- file_12th (file, optional) - 12th marksheet
- camera_data_10th (string, optional) - Base64 camera capture for 10th
- camera_data_12th (string, optional) - Base64 camera capture for 12th
```

**Response (200 - Success):**
```json
{
  "statusCode": 200,
  "responseData": {
    "message": "Educational documents processed successfully",
    "worker_id": "123",
    "documents": [
      {
        "class": "10th",
        "document_type": "marksheet",
        "qualification": "Class 10",
        "board": "CBSE",
        "stream": "Science",
        "year_of_passing": "2017",
        "school_name": "ST DON BOSCO COLLEGE LAKHIMPUR KHERI UP",
        "marks_type": "Percentage",
        "marks": "82.6%"
      },
      {
        "class": "12th",
        "document_type": "marksheet",
        "qualification": "Class 12",
        "board": "CBSE",
        "stream": "Science",
        "year_of_passing": "2019",
        "school_name": "ST DON BOSCO SENIOR SECONDARY SCHOOL",
        "marks_type": "CGPA",
        "marks": "8.5 CGPA"
      }
    ]
  }
}
```

**Processing Flow (Per Document):**
1. Validate file format
2. Convert camera if needed
3. Save file to /uploads/educational/{worker_id}/{class}/
4. Extract complete OCR text
5. LLM extraction using class-specific JSON schema (8 fields)
6. Save to DB
7. Return array of extracted documents

---

### 3. GET /form/worker/{worker_id}/verify
**Purpose:** Retrieve all data with cross-document verification

**Request:**
```
GET /form/worker/123/verify
```

**Response (200 - Verified):**
```json
{
  "statusCode": 200,
  "responseData": {
    "message": "All documents verified successfully",
    "verification_status": "verified",
    "comparisons": [
      {
        "type": "personal_vs_10th",
        "status": "matched",
        "details": {
          "name_similarity": 1.0,
          "dob_match": true
        }
      },
      {
        "type": "personal_vs_12th",
        "status": "matched",
        "details": {
          "name_similarity": 1.0,
          "dob_match": true
        }
      },
      {
        "type": "10th_vs_12th",
        "status": "matched",
        "details": {
          "name_similarity": 1.0,
          "dob_match": true
        }
      }
    ]
  }
}
```

**Response (400 - Verification Failed):**
```json
{
  "statusCode": 400,
  "responseData": {
    "message": "Document verification failed - see details",
    "verification_status": "failed",
    "error_code": "VERIFICATION_FAILED",
    "errors": [
      {
        "type": "name_mismatch",
        "comparison": "personal_vs_10th",
        "personal_value": "JOHN KUMAR SINGH",
        "document_value": "JOHN K SINGH",
        "similarity": 0.92,
        "threshold": 0.85
      }
    ]
  }
}
```

**Response (206 - Incomplete):**
```json
{
  "statusCode": 206,
  "responseData": {
    "message": "Incomplete verification - missing documents",
    "verification_status": "incomplete",
    "error_code": "INCOMPLETE_DATA"
  }
}
```

**Processing Flow:**
1. Retrieve personal data from DB
2. Retrieve 10th document (if exists)
3. Retrieve 12th document (if exists)
4. Perform cross-document comparisons
5. Update worker verification status
6. Log verification results
7. Return verification status and details

---

## Core Services

### 1. document_processor.py
**Functions:**
- `validate_document_format(filename)` - Check if file is PDF/JPG/PNG
- `is_camera_capture(data)` - Detect base64 camera capture
- `convert_camera_to_image(base64_data)` - Convert base64 to PIL Image
- `save_uploaded_file(content, filename, worker_id, doc_type, base_dir)` - Save file to disk
- `save_pil_image_to_file(image, worker_id, doc_type, base_dir)` - Save PIL Image to disk
- `get_document_type(file_path)` - Determine if PDF or Image

**Usage:** File validation and storage operations

---

### 2. ocr_service.py (Enhanced)
**Functions:**
- `ocr_to_text(file_path)` - Main entry point with multi-strategy fallback

**Extraction Strategy (Cascading):**
1. If PDF: Try native text extraction (pdfplumber)
2. If fails: Convert PDF to images (pdf2image at 300 DPI)
3. Use PaddleOCR on images
4. If fails: Use Tesseract as fallback
5. For JPG/PNG: Direct PaddleOCR with Tesseract fallback

**Quality Validation:**
- Minimum 50 characters extracted
- Timeout: 30 seconds per document
- Max PDF pages: 10

**Usage:** Complete OCR extraction of documents

---

### 3. llm_document_extractor.py
**Functions:**
- `extract_personal_data(raw_ocr_text)` - Extract 3 fields (name, DOB, address)
- `extract_10th_data(raw_ocr_text)` - Extract 8 fields for 10th marksheet
- `extract_12th_data(raw_ocr_text)` - Extract 8 fields for 12th marksheet
- `_build_*_prompt(raw_ocr_text)` - Build LLM prompts with JSON schema
- `_call_llm(prompt)` - Call OpenAI API and parse JSON response

**LLM Configuration:**
- Model: GPT-4
- Temperature: 0.3 (for consistent output)
- Max tokens: 2000
- Timeout: 30 seconds

**Usage:** Structured data extraction using LLM

---

### 4. document_verifier.py
**Functions:**
- `fuzzy_match_name(name1, name2, threshold=0.85)` - Levenshtein distance similarity
- `exact_match_dob(dob1, dob2)` - Exact DOB matching (YYYY-MM-DD)
- `compare_documents(doc1, doc2, comparison_type)` - Compare two documents
- `verify_worker_documents(personal, edu_10th, edu_12th)` - Overall verification
- `extract_verification_errors(verification_result)` - Format errors for response

**Verification Rules:**
- Name similarity >= 85% threshold
- DOB must match exactly
- Comparisons: personal vs 10th, personal vs 12th, 10th vs 12th

**Usage:** Cross-document verification logic

---

## Database Schema

### New Columns (workers table):
```sql
verification_status VARCHAR(50) - 'verified', 'failed', 'pending'
verified_at TIMESTAMP - When verification completed
verification_errors JSON - Stores mismatch details
```

### New Columns (educational_documents table):
```sql
document_class VARCHAR(10) - '10th' or '12th'
raw_ocr_text LONGTEXT - Complete OCR output
extracted_data JSON - Structured extracted fields
file_path VARCHAR(500) - File location
extraction_status VARCHAR(50) - 'success' or 'failed'
verification_flag VARCHAR(50) - 'verified' or 'failed'
```

### New Tables:

**document_extraction_log:**
```sql
id INT PRIMARY KEY
worker_id TEXT
extraction_type TEXT - 'personal', '10th', '12th'
raw_ocr_text LONGTEXT
extracted_data JSON
file_path VARCHAR(500)
extraction_status VARCHAR(50)
error_message VARCHAR(500)
created_at TIMESTAMP
```

**document_verification_log:**
```sql
id INT PRIMARY KEY
worker_id TEXT
verification_type TEXT - 'personal_vs_10th', etc
comparison_result JSON
verification_status VARCHAR(50)
created_at TIMESTAMP
```

---

## New CRUD Functions (db/crud.py)

1. `save_document_extraction(worker_id, extraction_type, raw_ocr_text, extracted_data, file_path, extraction_status, error_message)`
2. `get_educational_document(worker_id, class_level)` - Get 10th or 12th
3. `update_worker_verification_status(worker_id, verification_status, verification_errors)`
4. `save_verification_log(worker_id, verification_type, comparison_result, verification_status)`
5. `update_educational_document_extraction(worker_id, document_class, extracted_data, raw_ocr_text, file_path)`
6. `get_worker_complete_data(worker_id)` - Get all personal and educational data

---

## File Structure

**Modified Files:**
- `/db/database.py` - Added schema migrations
- `/db/crud.py` - Added 6 new functions
- `/config.py` - Added OCR/LLM config variables
- `/main.py` - Registered enhanced_router

**New Files:**
- `/services/document_processor.py` - File validation & processing
- `/services/llm_document_extractor.py` - LLM extraction logic
- `/services/document_verifier.py` - Verification logic
- `/api/document_endpoints.py` - 3 new API endpoints
- `/requirements.txt` - Dependencies

---

## Configuration (config.py)

```python
# OCR Configuration
OCR_PDF_MAX_PAGES = 10
OCR_PDF_DPI = 300
OCR_MIN_TEXT_LENGTH = 50
OCR_TIMEOUT = 30

# LLM Configuration
OPENAI_API_KEY = "your_key"
LLM_MODEL = "gpt-4"
LLM_TEMPERATURE = 0.3

# Verification Configuration
VERIFICATION_NAME_THRESHOLD = 0.85
VERIFICATION_DOB_EXACT = true

# File Upload
UPLOAD_MAX_SIZE_MB = 20
ALLOWED_EXTENSIONS = ["pdf", "jpg", "jpeg", "png"]
```

---

## Error Handling

**OCR Errors (400):**
- `OCR_EXTRACTION_FAILED` - All OCR strategies failed
- `INVALID_FILE_FORMAT` - File not PDF/JPG/PNG
- `CAMERA_CONVERSION_FAILED` - Base64 to image conversion failed
- `FILE_SAVE_FAILED` - Unable to save file to disk

**LLM Errors (400):**
- `LLM_EXTRACTION_FAILED` - LLM response parsing failed
- Fallback to partial data with null values

**Verification Errors (400):**
- `VERIFICATION_FAILED` - Document mismatch detected
- `INCOMPLETE_DATA` (206) - Missing required documents

**Database Errors (500):**
- `DATABASE_SAVE_FAILED` - DB write operation failed

---

## Response Status Codes

| Code | Scenario |
|------|----------|
| 200 | Successful extraction/verification |
| 206 | Partial data (incomplete verification) |
| 400 | OCR/LLM/Verification failure |
| 404 | Worker not found |
| 500 | Internal server error |

---

## Dependencies (requirements.txt)

```
# PDF Processing
pdfplumber==0.9.0
pdf2image==1.16.3
PyPDF2==3.0.1

# OCR Engines
pytesseract==0.3.10
paddleocr==2.7.0.3

# Image Processing
Pillow==10.0.0
opencv-python==4.8.0.74

# LLM & API
openai==1.3.0

# Text Processing
python-Levenshtein==0.21.1
fuzzywuzzy==0.18.0

# Web Framework
fastapi==0.104.0
uvicorn==0.24.0
python-multipart==0.0.6

# Database
SQLAlchemy==2.0.0
pymysql==1.1.0
```

---

## Implementation Verification

### OCR Logic Verification:
✓ Endpoint calls `ocr_to_text(file_path)` from ocr_service.py  
✓ ocr_to_text implements 4-level fallback strategy  
✓ Native PDF → PDF-to-Image + PaddleOCR → PDF-to-Image + Tesseract → Direct Image OCR  
✓ Quality validation checks minimum 50 characters  
✓ Complete raw OCR text is passed to LLM  

### LLM Extraction Verification:
✓ Complete raw OCR text passed (not fragments)  
✓ JSON schema included in prompt  
✓ LLM extracts ONLY specified fields  
✓ Personal: 3 fields (name, DOB, address)  
✓ Educational: 8 fields (document_type, qualification, board, stream, year_of_passing, school_name, marks_type, marks)  

### Verification Logic Verification:
✓ Cross-document comparisons implemented  
✓ Fuzzy name matching with 85% threshold  
✓ Exact DOB matching in YYYY-MM-DD format  
✓ Comparisons logged to verification_log table  
✓ Worker verification_status updated in DB  

### No Breaking Changes:
✓ All modifications are additive  
✓ New columns added safely with defaults  
✓ New tables created independently  
✓ Existing endpoints unmodified  
✓ Backward compatibility maintained  

---

## Summary

The Document Extraction & Verification system is fully implemented with:
- **3 robust API endpoints** handling upload and verification
- **4 core services** for processing, extraction, and verification
- **Multi-strategy OCR** with 4-level fallback mechanism
- **LLM-based structured extraction** using JSON schema
- **Cross-document verification** with fuzzy matching
- **Comprehensive audit logging** for extraction and verification
- **Standardized error handling** with clear error codes
- **Zero breaking changes** to existing code
