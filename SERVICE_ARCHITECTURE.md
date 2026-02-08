# Service Integration Architecture & Data Models

## Complete Service Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       FRONTEND/CLIENT LAYER                            │
├─────────────────────────────────────────────────────────────────────────┤
│ • Mobile App / Web Frontend                                            │
│ • Upload personal document (file or camera)                           │
│ • Upload educational documents (file or camera)                       │
│ • Poll for verification status                                        │
└──────────────────┬──────────────────────────────────────────────────────┘
                   │
                   ├─────────────────────────────────────────────────────────┐
                   │                                                          │
        ┌──────────▼────────────┐                            ┌──────────────▼────────────┐
        │  POST /form/personal  │                            │ POST /form/educational    │
        │      /upload          │                            │     /upload               │
        │   (Sync Return 200)   │                            │  (Sync Return 200)       │
        └──────────┬────────────┘                            └───────────┬──────────────┘
                   │                                                     │
        ┌──────────▼──────────────────────────────────────────────────────▼──────┐
        │                    DOCUMENT PROCESSOR SERVICE                          │
        ├────────────────────────────────────────────────────────────────────────┤
        │ 1. Validate file format (PDF, JPG, PNG)                              │
        │ 2. Convert camera data (base64) to image if needed                  │
        │ 3. Save to disk                                                     │
        │ 4. Determine document class ('10th', '12th', 'personal')           │
        │                                                                     │
        │ Functions:                                                          │
        │ • validate_document_format()                                       │
        │ • is_camera_capture()                                             │
        │ • convert_camera_to_image()                                       │
        │ • get_file_extension()                                            │
        └──────────┬──────────────────────────────────────────────────────────┘
                   │
                   ├─ Save metadata in DB
                   ├─ Return upload_id to client
                   └─ Trigger async background job
                      │
        ┌─────────────▼────────────────────────────────────────────────────┐
        │           BACKGROUND JOB ORCHESTRATION                          │
        │         (services/background_jobs.py)                          │
        ├────────────────────────────────────────────────────────────────┤
        │                                                                │
        │ Job Queue:                                                   │
        │ ┌─────────────────────────────────────────────────────────┐ │
        │ │ upload_id_1: {status: pending, type: ocr}             │ │
        │ │ upload_id_2: {status: processing, type: llm_extract}  │ │
        │ │ upload_id_3: {status: completed, type: verification}  │ │
        │ └─────────────────────────────────────────────────────────┘ │
        │                                                                │
        │ Processing Pipeline:                                         │
        │                                                                │
        │ Step 1: OCR EXTRACTION                                       │
        │ ┌────────────────────────────────────────────────────────┐   │
        │ │ Call OCR Service with file_path                       │   │
        │ │ ├─ If PDF: Use pdfplumber or PaddleOCR             │   │
        │ │ ├─ If Image: Use PaddleOCR or Tesseract            │   │
        │ │ └─ Returns: raw_ocr_text (str)                     │   │
        │ └────────────┬───────────────────────────────────────┘   │
        │              │                                              │
        │ Step 2: LLM EXTRACTION                                    │
        │ ┌────────────▼───────────────────────────────────────┐   │
        │ │ Call LLM Document Extractor with raw_ocr_text     │   │
        │ │ ├─ Select prompt based on document_class          │   │
        │ │ ├─ Call OpenAI API (or other LLM)                │   │
        │ │ ├─ Parse JSON response                            │   │
        │ │ ├─ Extract: {name, dob, address, marks, etc}    │   │
        │ │ ├─ Calculate: confidence_scores                  │   │
        │ │ ├─ Calculate: percentage (for marksheets)         │   │
        │ │ └─ Returns: {extracted_data, confidence_scores}  │   │
        │ └────────────┬───────────────────────────────────────┘   │
        │              │                                              │
        │ Step 3: SAVE TO DATABASE                                  │
        │ ┌────────────▼───────────────────────────────────────┐   │
        │ │ crud.save_document_with_extraction()              │   │
        │ │ ├─ Update educational_documents table OR          │   │
        │ │ ├─ Update workers table (personal)                │   │
        │ │ └─ Set extraction_status = "completed"            │   │
        │ └────────────┬───────────────────────────────────────┘   │
        │              │                                              │
        │ Step 4: VERIFICATION (If all docs uploaded)               │
        │ ┌────────────▼───────────────────────────────────────┐   │
        │ │ Call Document Verifier:                            │   │
        │ │ ├─ Get all documents for worker                   │   │
        │ │ ├─ Compare personal vs 10th, personal vs 12th,    │   │
        │ │ │  10th vs 12th                                    │   │
        │ │ ├─ Fuzzy match names (threshold: 85%)             │   │
        │ │ ├─ Exact match DOBs and addresses                 │   │
        │ │ ├─ Generate comparison results                    │   │
        │ │ └─ Returns: {overall_status, comparisons, mismatches} │
        │ └────────────┬───────────────────────────────────────┘   │
        │              │                                              │
        │ Step 5: UPDATE VERIFICATION STATUS                        │
        │ ┌────────────▼───────────────────────────────────────┐   │
        │ │ Update workers.verification_status                │   │
        │ │ Update educational_documents.verification_flag     │   │
        │ │ Create document_verification_log entry             │   │
        │ │ Mark job status = "completed"                      │   │
        │ └────────────┬───────────────────────────────────────┘   │
        │              │                                              │
        │ Job Complete ✓                                            │
        └──────────────┘                                             
```

---

## Data Model: Complete Document Extraction Workflow

```
PERSONAL DOCUMENT
    │
    ├─ OCR Extraction
    │  └─ raw_ocr_text: "BABU KHAN\nDOB: 01-12-1987\nAddress: ..."
    │
    ├─ LLM Processing (with prompt)
    │  └─ Prompt: "Extract name, DOB (YYYY-MM-DD), address, mobile"
    │
    ├─ Extracted Data
    │  └─ {
    │      "name": "BABU KHAN",
    │      "dob": "1987-12-01",
    │      "address": "KAMLA RAMAN NAGAR, BANGALORE",
    │      "mobile": "7905285898"
    │    }
    │
    └─ Confidence Scores
       └─ {
          "name": 0.98,
          "dob": 0.99,
          "address": 0.92,
          "mobile": 0.97
       }

┌─────────────────────────────────────────────────────────────────┐

10TH MARKSHEET
    │
    ├─ OCR Extraction
    │  └─ raw_ocr_text: "CLASS 10\nBOARD: CBSE\nMATHS: 85\n..."
    │
    ├─ LLM Processing (with 10th-specific prompt)
    │  └─ Prompt: "This is 10th marksheet. Extract marks by subject,
    │             board, percentage. Calculate if not shown."
    │
    ├─ Extracted Data
    │  └─ {
    │      "class": "10th",
    │      "board": "CBSE",
    │      "marks": {
    │        "math": 85,
    │        "english": 78,
    │        "science": 82,
    │        "social": 80,
    │        "hindi": 75
    │      },
    │      "total_obtained": 400,
    │      "total_possible": 500,
    │      "percentage": 80.0
    │    }
    │
    └─ Confidence Scores
       └─ {
          "board": 0.95,
          "marks": 0.92,
          "percentage": 0.99
       }

┌─────────────────────────────────────────────────────────────────┐

12TH MARKSHEET
    │
    ├─ OCR Extraction
    │  └─ raw_ocr_text: "CLASS 12\nBOARD: STATE\nMATHS: 88\n..."
    │
    ├─ LLM Processing (with 12th-specific prompt)
    │  └─ Prompt: "12th marksheet. Extract marks, board, calculate:
    │             percentage = (total_obtained / total_possible) * 100"
    │
    ├─ Extracted Data
    │  └─ {
    │      "class": "12th",
    │      "board": "State Board",
    │      "marks": {
    │        "math": 88,
    │        "english": 85,
    │        "science": 90,
    │        "social": 82
    │      },
    │      "total_obtained": 345,
    │      "total_possible": 400,
    │      "calculated_percentage": 86.25
    │    }
    │
    └─ Confidence Scores
       └─ {
          "board": 0.93,
          "marks": 0.93,
          "percentage": 0.99
       }

┌─────────────────────────────────────────────────────────────────┐

VERIFICATION PROCESS
    │
    ├─ Compare personal vs 10th
    │  ├─ Name: "BABU KHAN" vs "BABU KHAN" → fuzzy_match (95%) → ✓ PASS
    │  ├─ DOB: "1987-12-01" vs "1987-12-01" → exact_match → ✓ PASS
    │  └─ Address: Compare → ✓ PASS
    │
    ├─ Compare personal vs 12th
    │  ├─ Name: "BABU KHAN" vs "BABU KHAN" → ✓ PASS
    │  ├─ DOB: "1987-12-01" vs "1987-12-01" → ✓ PASS
    │  └─ Address: Compare → ✓ PASS
    │
    ├─ Compare 10th vs 12th
    │  ├─ Name: "BABU KHAN" vs "BABU KHAN" → ✓ PASS
    │  └─ DOB: "1987-12-01" vs "1987-12-01" → ✓ PASS
    │
    └─ Verification Result
       └─ {
          "overall_status": "verified",
          "comparisons": [
            {"type": "personal_vs_10th", "result": "passed"},
            {"type": "personal_vs_12th", "result": "passed"},
            {"type": "10th_vs_12th", "result": "passed"}
          ],
          "mismatches": []
       }
```

---

## Database Schema Relationships

```
┌──────────────────────────────────────────────────────────────────┐
│                         WORKERS TABLE                            │
├──────────────────────────────────────────────────────────────────┤
│ worker_id (PK)                                                   │
│ mobile_number                                                    │
│ name (extracted from personal document)                         │
│ dob (extracted from personal document)                          │
│ address (extracted from personal document)                      │
│ personal_document_path                                           │
│ educational_document_paths (JSON array)                         │
│ created_at                                                       │
│ ─────────────── NEW ───────────────────────────────────────────│
│ verification_status (verified, pending, failed)                │
│ verified_at (timestamp)                                         │
│ verification_errors (JSON with mismatch details)               │
│ last_verified_document_set                                      │
└──────────────────────────────────────────────────────────────────┘
         │
         │ 1:N relationship
         │
         ▼
┌──────────────────────────────────────────────────────────────────┐
│              EDUCATIONAL_DOCUMENTS TABLE                         │
├──────────────────────────────────────────────────────────────────┤
│ id (PK)                                                          │
│ worker_id (FK)                                                   │
│ document_type                                                    │
│ qualification                                                    │
│ board                                                            │
│ stream                                                           │
│ year_of_passing                                                  │
│ school_name                                                      │
│ marks_type                                                       │
│ marks (JSON)                                                     │
│ percentage                                                       │
│ created_at                                                       │
│ ─────────────── NEW ───────────────────────────────────────────│
│ document_class (10th, 12th, other)                              │
│ raw_ocr_text (for debugging/audit)                             │
│ marks_data (JSON: {subject: marks})                            │
│ calculated_percentage (auto-calc from marks)                    │
│ extracted_name (from LLM extraction)                            │
│ extracted_dob (from LLM extraction)                             │
│ extracted_address (from LLM extraction)                         │
│ verification_flag (verified, pending, failed)                   │
│ confidence_scores (JSON: {name: 0.95, dob: 0.98})              │
└──────────────────────────────────────────────────────────────────┘
         │
         │ 1:N relationship
         │
         ▼
┌──────────────────────────────────────────────────────────────────┐
│         DOCUMENT_VERIFICATION_LOG TABLE (NEW)                    │
├──────────────────────────────────────────────────────────────────┤
│ id (PK)                                                          │
│ worker_id (FK)                                                   │
│ verification_type (personal_vs_10th, etc.)                      │
│ document_1_type                                                  │
│ document_2_type                                                  │
│ name_match (boolean)                                             │
│ dob_match (boolean)                                              │
│ address_match (boolean)                                          │
│ result (passed, failed)                                          │
│ mismatch_details (JSON with field-level mismatches)             │
│ created_at                                                       │
└──────────────────────────────────────────────────────────────────┘
```

---

## Request/Response Flow Examples

### UPLOAD FLOW

```
CLIENT REQUEST:
POST /form/personal/upload
{
  "upload_type": "file",
  "document_type": "aadhar"
  + multipart file: personal_doc.pdf
}

┌─────────────────────────────────────┐
│ INSTANT RESPONSE (Sync - 200)       │
├─────────────────────────────────────┤
│ {                                   │
│   "statusCode": 200,                │
│   "responseData": {                 │
│     "message": "Doc uploaded",     │
│     "worker_id": "uuid-123",        │
│     "upload_id": "upload_abc",      │
│     "processing_status": "queued"   │
│   }                                 │
│ }                                   │
└─────────────────────────────────────┘
           │
           └─ Background job created
              └─ OCR → LLM → Save → Verify
```

### RETRIEVAL FLOW - STILL PROCESSING

```
CLIENT REQUEST:
GET /form/worker/uuid-123/data?wait_for_processing=false

┌────────────────────────────────────────┐
│ RESPONSE (Async - 202)                 │
├────────────────────────────────────────┤
│ {                                      │
│   "statusCode": 202,                   │
│   "responseData": {                    │
│     "message": "Processing...",        │
│     "processing_status": "processing", │
│     "estimated_time_seconds": 30,      │
│     "jobs": [                          │
│       {                                │
│         "upload_id": "upload_abc",     │
│         "type": "ocr",                 │
│         "status": "processing",        │
│         "progress": 45                 │
│       }                                │
│     ]                                  │
│   }                                    │
│ }                                      │
└────────────────────────────────────────┘
           │
           └─ Client polls again in 5 seconds
```

### RETRIEVAL FLOW - COMPLETE & VERIFIED

```
CLIENT REQUEST:
GET /form/worker/uuid-123/data?include_verification=true

┌──────────────────────────────────────┐
│ RESPONSE (Complete - 200)             │
├──────────────────────────────────────┤
│ {                                    │
│   "statusCode": 200,                 │
│   "responseData": {                  │
│     "worker": {                      │
│       "worker_id": "uuid-123",       │
│       "name": "BABU KHAN",           │
│       "dob": "1987-12-01",           │
│       "address": "...",              │
│       "verified": true,              │
│       "verified_at": "2026-02-07T..." │
│     },                               │
│     "personal": {                    │
│       "name": "BABU KHAN",           │
│       "confidence_scores": {...}     │
│     },                               │
│     "education": [                   │
│       {                              │
│         "document_class": "10th",    │
│         "percentage": 80.0,          │
│         "calculated_percentage": ... │
│       },                             │
│       {                              │
│         "document_class": "12th",    │
│         "calculated_percentage": 86.25 │
│       }                              │
│     ],                               │
│     "verification": {                │
│       "overall_status": "verified",  │
│       "mismatches": []               │
│     }                                │
│   }                                  │
│ }                                    │
└──────────────────────────────────────┘
```

### RETRIEVAL FLOW - VERIFICATION FAILED

```
CLIENT REQUEST:
GET /form/worker/uuid-456/data?include_verification=true

┌──────────────────────────────────────┐
│ RESPONSE (Verification Failed - 400)  │
├──────────────────────────────────────┤
│ {                                    │
│   "statusCode": 400,                 │
│   "responseData": {                  │
│     "message": "Verification failed",│
│     "verification": {                │
│       "overall_status": "failed",    │
│       "mismatches": [                │
│         {                            │
│           "comparison": "personal..." │
│           "field": "name",           │
│           "personal_value": "BABU",  │
│           "document_value": "BABUU", │
│           "match": false             │
│         }                            │
│       ]                              │
│     }                                │
│   }                                  │
│ }                                    │
└──────────────────────────────────────┘
           │
           └─ Frontend shows: "Documents don't match"
              Prompt user to upload correct docs
```

---

## Service Dependencies & Environment Variables

### Required Libraries
```
pdfplumber==0.10.5        # PDF text extraction
python-Levenshtein==0.22  # Fuzzy string matching
openai==1.3.0             # LLM API calls
paddleocr==2.7.0.3        # Image OCR (if available)
pytesseract==0.3.10       # Tesseract OCR (if available)
```

### Environment Variables
```
# LLM Configuration
LLM_API_KEY=<your-openai-api-key>
LLM_MODEL=gpt-4-turbo-preview
LLM_TEMPERATURE=0.3  # Lower = more consistent extraction

# Verification Configuration
VERIFICATION_NAME_THRESHOLD=0.85  # Fuzzy match threshold (0-1)
VERIFICATION_DOB_EXACT=true       # DOB must match exactly
VERIFICATION_ADDRESS_THRESHOLD=0.75

# Job Configuration
JOB_TIMEOUT_SECONDS=120
JOB_RETRY_ATTEMPTS=3
JOB_RETRY_BACKOFF_SECONDS=5

# Processing Configuration
MAX_FILE_SIZE_MB=50
SUPPORTED_FORMATS=pdf,jpg,jpeg,png
```

---

## Error Handling Strategy

```
UPLOAD ERROR
├─ Format validation failed
│  └─ Return 400 + validation_error
├─ File too large
│  └─ Return 413 + file_size_error
└─ Disk space
   └─ Return 507 + storage_error

PROCESSING ERROR
├─ OCR failed
│  ├─ Log error
│  ├─ Retry up to 3 times
│  └─ Mark job failed
├─ LLM API error
│  ├─ Timeout → retry with backoff
│  ├─ Invalid response → save raw text
│  └─ Mark job failed
└─ Database error
   ├─ Log critical error
   └─ Mark job failed

VERIFICATION ERROR
├─ Missing documents
│  └─ Partial verification
├─ Data mismatch
│  ├─ Store details in mismatch_details
│  ├─ Mark as failed
│  └─ Return 400 with details
└─ Low confidence
   ├─ Flag for manual review
   └─ Update verification_flag
```

