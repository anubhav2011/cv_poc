# Implementation Plan Summary - New LLM-Based Services

## RECOMMENDED CHANGES BREAKDOWN

Based on my analysis of the codebase and your requirements document, here are all the changes needed:

---

## PHASE 1: DATABASE SCHEMA UPDATES

### Changes to workers table
```sql
ALTER TABLE workers ADD COLUMN (
  verification_status TEXT DEFAULT NULL,
  verified_at TIMESTAMP DEFAULT NULL,
  verification_errors TEXT DEFAULT NULL,
  last_verified_document_set TEXT DEFAULT NULL
);
```

### Changes to educational_documents table
```sql
ALTER TABLE educational_documents ADD COLUMN (
  document_class TEXT,
  raw_ocr_text TEXT,
  marks_data TEXT,
  calculated_percentage REAL,
  extracted_name TEXT,
  extracted_dob TEXT,
  extracted_address TEXT,
  verification_flag TEXT DEFAULT NULL,
  confidence_scores TEXT
);
```

### New table: document_verification_log
```sql
CREATE TABLE document_verification_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  worker_id TEXT NOT NULL,
  verification_type TEXT,
  document_1_type TEXT,
  document_2_type TEXT,
  name_match BOOLEAN,
  dob_match BOOLEAN,
  address_match BOOLEAN,
  result TEXT,
  mismatch_details TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
);
```

---

## PHASE 2: NEW SERVICE FILES TO CREATE

### 1. services/document_processor.py (NEW)
**Purpose:** Handle multi-format document uploads, validation, and conversion

**Key Functions:**
- `validate_document_format(file: File) -> bool` - Validate PDF/JPG/PNG only
- `is_camera_capture(data: str) -> bool` - Detect base64 camera data
- `convert_camera_to_image(base64_data: str, output_path: str) -> str` - Convert base64 to image
- `get_file_extension(file) -> str` - Extract file extension
- `extract_raw_text(file_path: str, document_type: str) -> str` - Route to OCR service

**Responsibilities:**
- Accept file or camera (base64) uploads
- Validate file format (PDF, JPG, PNG only)
- Save files to appropriate directories
- Call OCR service with correct format handling

---

### 2. services/llm_document_extractor.py (NEW)
**Purpose:** Extract structured data from OCR text using LLM with confidence scoring

**Key Functions:**
- `extract_personal_data(raw_ocr_text: str) -> dict` - Extract name, DOB, address, mobile
- `extract_10th_data(raw_ocr_text: str) -> dict` - Extract 10th marksheet data
- `extract_12th_data(raw_ocr_text: str) -> dict` - Extract 12th marksheet data
- `parse_marks_table(table_text: str) -> dict` - Parse subject marks
- `calculate_percentage_from_marks(marks: dict, total_possible: int) -> float` - Auto-calculate percentage

**Returns:**
```python
{
  "extracted_data": {
    "name": "BABU KHAN",
    "dob": "01-12-1987",
    ...
  },
  "confidence_scores": {
    "name": 0.95,
    "dob": 0.98,
    ...
  },
  "raw_extraction": "full LLM response"
}
```

**Responsibilities:**
- Call OpenAI API with class-specific prompts
- Parse JSON responses from LLM
- Calculate confidence scores for each field
- Handle missing or ambiguous data gracefully
- Calculate percentages from marks tables

---

### 3. services/document_verifier.py (NEW)
**Purpose:** Verify documents match across multiple uploads

**Key Functions:**
- `fuzzy_match_name(name1: str, name2: str, threshold: float = 0.85) -> bool` - Fuzzy match names
- `exact_match_dob(dob1: str, dob2: str) -> bool` - Exact DOB comparison
- `normalize_name(name: str) -> str` - Normalize names for comparison
- `compare_documents(documents: List[dict]) -> dict` - Compare all document pairs
- `get_verification_status(comparison_result: dict) -> str` - Determine pass/fail

**Returns:**
```python
{
  "overall_status": "verified" | "failed",
  "comparisons": [
    {
      "type": "personal_vs_10th",
      "name_match": True,
      "dob_match": True,
      "address_match": True,
      "result": "passed"
    }
  ],
  "mismatches": [
    {
      "comparison": "personal_vs_10th",
      "field": "name",
      "value_1": "BABU KHAN",
      "value_2": "BABU KHANN",
      "match": False
    }
  ]
}
```

**Responsibilities:**
- Compare extracted data across documents
- Use fuzzy matching for names (threshold: 85%)
- Use exact matching for DOBs
- Generate detailed mismatch reports
- Support partial verification (if only some documents present)

---

### 4. services/background_jobs.py (NEW)
**Purpose:** Manage asynchronous OCR/LLM processing jobs

**Key Functions:**
- `create_ocr_job(worker_id: str, file_path: str, document_type: str, upload_id: str) -> str` - Create job record
- `process_ocr_job(job_id: str) -> dict` - Execute OCR extraction
- `process_llm_extraction(job_id: str, raw_text: str, document_class: str) -> dict` - Run LLM extraction
- `process_verification(worker_id: str) -> dict` - Run cross-document verification
- `get_job_status(upload_id: str) -> dict` - Get job progress
- `mark_job_complete(upload_id: str, result_data: dict) -> bool` - Mark job done

**Job Status Flow:**
```
pending → processing → completed (success) OR failed (error)
        ↓
      error → retry (up to 3 times)
```

**Responsibilities:**
- Manage job queue with status tracking
- Execute async OCR/LLM/verification workflows
- Handle retries on failure (exponential backoff)
- Store job results in database
- Provide job status for client polling

---

## PHASE 3: MODIFY EXISTING SERVICE

### services/ocr_service.py (ENHANCE)
**New Capabilities:**
- Add PDF support using `pdfplumber` library
- Detect if PDF is native text or scanned
- For scanned PDFs: Fall back to PaddleOCR on converted images
- Keep existing image OCR logic (PaddleOCR/Tesseract)

**New Functions:**
- `extract_text_from_pdf(pdf_path: str) -> str` - Extract from native PDFs
- `extract_text_from_scanned_pdf(pdf_path: str) -> str` - OCR scanned PDFs
- `is_native_pdf(pdf_path: str) -> bool` - Detect PDF type

---

## PHASE 4: CRUD LAYER UPDATES

### db/crud.py - NEW FUNCTIONS

```python
def save_document_with_extraction(
    worker_id: str,
    document_type: str,  # 'personal', '10th', '12th'
    file_path: str,
    raw_ocr_text: str,
    extracted_data: dict,  # JSON from LLM
    confidence_scores: dict
) -> bool:
    """Save document with full extraction metadata"""

def get_document_extraction_status(
    worker_id: str,
    document_type: str = None
) -> dict:
    """Get extraction status for document(s)"""

def update_verification_status(
    worker_id: str,
    status: str,  # 'verified', 'pending', 'failed'
    verification_details: dict
) -> bool:
    """Update worker verification status"""

def save_verification_log(
    worker_id: str,
    comparison_type: str,
    result: str,  # 'passed', 'failed'
    details: dict
) -> bool:
    """Create audit log entry for verification"""

def get_all_worker_documents_for_verification(worker_id: str) -> list:
    """Get all documents for cross-verification"""

def get_verification_status(worker_id: str) -> dict:
    """Get detailed verification results"""
```

### db/crud.py - MODIFY EXISTING FUNCTIONS

- `update_worker_data()` - Add confidence scores parameter
- `save_educational_document()` - Add document_class, confidence_scores parameters
- `get_educational_documents()` - Return additional extraction metadata

---

## PHASE 5: API ENDPOINT REFACTORING

### POST /form/personal/upload (MODIFY)

**New Parameters:**
- `upload_type`: "file" or "camera"
- `camera_data`: base64 string if upload_type="camera"
- `document_type`: document type identifier

**New Response Format:**
```json
{
  "statusCode": 200,
  "responseData": {
    "message": "Personal document uploaded successfully",
    "worker_id": "36d4699e-f894...",
    "upload_id": "upload_abc123",
    "file_name": "personal_doc.pdf",
    "processing_status": "queued"
  }
}
```

**Changes:**
- Return immediately (don't wait for OCR)
- Trigger background job for processing
- Return upload_id for status polling
- Use new document_processor service

---

### POST /form/educational/upload (MODIFY)

**New Parameters:**
- `upload_type`: "file" or "camera"
- `files`: List[File] for multiple files
- `camera_data`: List[str] for multiple camera captures
- `document_class`: ["10th", "12th"] - which class is which
- `document_count`: number of documents

**New Response Format:**
```json
{
  "statusCode": 200,
  "responseData": {
    "message": "2 educational documents uploaded successfully",
    "worker_id": "36d4699e-f894...",
    "uploads": [
      {
        "upload_id": "upload_def456",
        "document_class": "10th",
        "file_name": "10th_marksheet.pdf",
        "processing_status": "queued"
      },
      {
        "upload_id": "upload_ghi789",
        "document_class": "12th",
        "file_name": "12th_marksheet.png",
        "processing_status": "queued"
      }
    ]
  }
}
```

**Changes:**
- Support multiple files in single request
- Add document_class to classify uploads
- Return upload_id array for each file
- Trigger background jobs for each file

---

### GET /form/worker/{worker_id}/data (ENHANCE SIGNIFICANTLY)

**New Query Parameters:**
- `include_verification`: bool (default: true)
- `include_raw_ocr`: bool (default: false) - for debugging
- `wait_for_processing`: bool (default: false) - wait for jobs

**Response Changes:**

**Case 1: Still Processing (202)**
```json
{
  "statusCode": 202,
  "responseData": {
    "message": "Data processing in progress",
    "processing_status": "processing",
    "estimated_time_seconds": 30,
    "jobs": [
      {
        "upload_id": "upload_abc123",
        "type": "ocr",
        "status": "processing",
        "progress": 45
      }
    ]
  }
}
```

**Case 2: Complete & Verified (200)**
```json
{
  "statusCode": 200,
  "responseData": {
    "worker": {
      "worker_id": "36d4699e-f894...",
      "name": "BABU KHAN",
      "dob": "01-12-1987",
      "address": "KAMLA RAMAN NAGAR...",
      "verified": true,
      "verified_at": "2026-02-07T10:30:00Z"
    },
    "personal": {
      "name": "BABU KHAN",
      "dob": "01-12-1987",
      "address": "...",
      "confidence_scores": {
        "name": 0.98,
        "dob": 0.99,
        "address": 0.92
      }
    },
    "education": [
      {
        "document_class": "10th",
        "qualification": "SSC",
        "board": "CBSE",
        "marks": { "math": 85, "english": 78 },
        "percentage": 81.67,
        "confidence_scores": { "marks": 0.92, "percentage": 0.99 },
        "verification_flag": "verified"
      },
      {
        "document_class": "12th",
        "qualification": "HSC",
        "board": "State Board",
        "marks": { "math": 88, "english": 85 },
        "calculated_percentage": 87.67,
        "confidence_scores": { "marks": 0.93, "percentage": 0.99 },
        "verification_flag": "verified"
      }
    ],
    "verification": {
      "overall_status": "verified",
      "documents_verified": ["personal", "10th", "12th"],
      "comparisons": [
        {
          "type": "personal_vs_10th",
          "name_match": true,
          "dob_match": true,
          "result": "passed"
        }
      ],
      "mismatches": []
    },
    "message": "All data extracted and verified successfully"
  }
}
```

**Case 3: Verification Failed (400)**
```json
{
  "statusCode": 400,
  "responseData": {
    "message": "Document verification failed",
    "verification": {
      "overall_status": "failed",
      "mismatches": [
        {
          "comparison": "personal_vs_10th",
          "field": "name",
          "personal_value": "BABU KHAN",
          "document_value": "BABU KHANN",
          "match": false
        }
      ]
    }
  }
}
```

**Changes:**
- Check background job status first
- Return 202 if processing not complete
- Run verification when complete
- Return detailed verification results
- Show both percentage and calculated_percentage for education

---

## PHASE 6: RESPONSE FORMAT STANDARDIZATION

**All endpoints must return this format:**

```json
{
  "statusCode": 200|201|202|400|500,
  "responseData": {
    "message": "Human readable message",
    "data": { /* operation specific data */ },
    "errors": [ /* if error */ ]
  }
}
```

**Endpoints to standardize:**
- POST /form/signup
- POST /form/submit
- GET /form/worker/{id}/data
- POST /form/personal/upload
- POST /form/educational/upload
- All CV endpoints (if applicable)
- All experience endpoints (if applicable)

---

## SUMMARY OF FILES TO CREATE/MODIFY

### New Files (4)
1. ✅ `services/document_processor.py`
2. ✅ `services/llm_document_extractor.py`
3. ✅ `services/document_verifier.py`
4. ✅ `services/background_jobs.py`

### Modified Files (5)
1. 📝 `db/database.py` - Add migration code for new columns/table
2. 📝 `db/crud.py` - Add 6 new functions, modify 3 existing
3. 📝 `services/ocr_service.py` - Add PDF support
4. 📝 `api/form.py` - Refactor 3 endpoints, standardize responses
5. 📝 `db/models.py` - Add new response models for verification

### Documentation
1. 📄 `IMPLEMENTATION_WORKFLOW.md` ✅ (Created)
2. 📄 `IMPLEMENTATION_SUMMARY.md` ✅ (This file)

---

## Implementation Checklist

- [ ] Database migrations created and executed
- [ ] document_processor.py created with validation logic
- [ ] llm_document_extractor.py created with LLM integration
- [ ] document_verifier.py created with fuzzy matching
- [ ] background_jobs.py created with job queue
- [ ] ocr_service.py enhanced with PDF support
- [ ] CRUD functions added for verification
- [ ] Personal upload endpoint refactored
- [ ] Educational upload endpoint refactored
- [ ] Worker data endpoint enhanced
- [ ] All responses standardized
- [ ] Error handling implemented
- [ ] Background jobs tested
- [ ] Verification logic tested
- [ ] No existing functionality broken

---

## Success Criteria

1. ✅ All endpoints use new services in background
2. ✅ LLM extracts structured data with confidence scores
3. ✅ Percentage/CGPA displayed for both 10th and 12th
4. ✅ Verification compares all document pairs
5. ✅ All responses follow standardized format
6. ✅ No code is broken
7. ✅ Background processing handles async operations
8. ✅ Detailed error messages with mismatches

---

## Next Steps

Once you approve this plan, implementation will proceed in order:

1. **Day 1:** Database schema updates
2. **Days 2-3:** Create new services (document_processor, llm_extractor, verifier, jobs)
3. **Day 3:** Enhance OCR service with PDF support
4. **Day 4:** Update CRUD layer with new functions
5. **Day 5:** Refactor API endpoints
6. **Day 6:** Integration testing and fixes

All code will be production-ready, properly tested, and documented.

