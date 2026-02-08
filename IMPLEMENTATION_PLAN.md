# UPDATED IMPLEMENTATION PLAN: Document OCR with Always-Fetch Pattern

## Overview
Implement a background document processing system where OCR and LLM extraction happen automatically when **GET `/form/worker/{worker_id}/data`** is called.

---

## Key Requirement: Always-Fetch Pattern

**When GET `/form/worker/{worker_id}/data` is called:**
1. Check if any documents exist with `extraction_status = 'pending'`
2. **ALWAYS trigger background processing** for any unprocessed documents
3. Optionally wait for processing or return with status indicators
4. Return complete extracted data when available

---

## Implementation Phases

### PHASE 1: Create LLM Document Extractor Service
**File:** `services/llm_document_extractor.py`

**Purpose:** Extract structured data from raw OCR text using LLM

**Methods:**
```python
extract_personal_data(raw_ocr_text: str) -> dict
    # Extracts: name, dob (DD-MM-YYYY), address
    # Returns: JSON dict with these 3 fields

extract_educational_data(raw_ocr_text: str) -> dict
    # Extracts: document_type, qualification, board, stream, year_of_passing, school_name, marks_type, marks
    # Returns: JSON dict with these 8 fields
```

**LLM Prompts:**
- Personal: Extract name, dob, address from OCR text
- Educational: Extract all 8 fields from OCR text
- Return valid JSON only, null for missing fields

---

### PHASE 2: Enhance OCR Service
**File:** `services/ocr_service.py`

**New Method:**
```python
pdf_to_image(pdf_path: str) -> Optional[str]
    # Converts PDF first page to PNG image
    # Returns path to converted image or None if failed
```

**Enhancement to existing methods:**
- If PDF text extraction returns < 10 chars, convert to image and retry OCR
- Fallback mechanism: PDF → Image → OCR

---

### PHASE 3: Create Background Document Processor
**File:** `services/background_processor.py`

**Purpose:** Handle async document processing

**Methods:**
```python
process_personal_document(worker_id: str, document_path: str) -> dict
    # 1. Extract OCR text from document
    # 2. Call LLM to extract personal data
    # 3. Update workers table with extracted data
    # 4. Update status to 'completed'
    # Returns: result dict with status and extracted data

process_educational_document(worker_id: str, document_path: str) -> dict
    # 1. Extract OCR text from document
    # 2. Call LLM to extract educational data
    # 3. Save/update educational_documents table
    # 4. Update status to 'completed'
    # Returns: result dict with status and extracted data

trigger_document_processing(worker_id: str) -> None
    # Check for pending documents
    # Queue background jobs for processing
```

---

### PHASE 4: Update Database CRUD Operations
**File:** `db/crud.py`

**New Functions:**
```python
update_personal_extraction_status(worker_id: str, status: str) -> bool
    # Update workers.personal_extraction_status

update_personal_extracted_data(worker_id: str, data: dict) -> bool
    # Update name, dob, address + status

update_educational_extraction_status(document_id: str, status: str) -> bool
    # Update educational_documents.extraction_status

update_educational_extracted_data(document_id: str, data: dict) -> bool
    # Update all extracted fields + status

get_pending_personal_documents(worker_id: str) -> list
    # Get personal documents with extraction_status = 'pending'

get_pending_educational_documents(worker_id: str) -> list
    # Get educational documents with extraction_status = 'pending'
```

---

### PHASE 5: Update Database Schema
**SQL Migrations:**

```sql
-- Add status column to workers table (for personal documents)
ALTER TABLE workers ADD COLUMN IF NOT EXISTS personal_extraction_status VARCHAR(20) DEFAULT 'pending';

-- Add extracted data and status columns to educational_documents
ALTER TABLE educational_documents ADD COLUMN IF NOT EXISTS extraction_status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE educational_documents ADD COLUMN IF NOT EXISTS raw_ocr_text TEXT;
```

---

### PHASE 6: Update API Response Models
**File:** `db/models.py`

**Enhance existing models:**
```python
WorkerDataResponse:
    - Add processing_status field
    - Add extraction_metadata field (optional)

EducationalDocument:
    - Verify all 8 fields are present
    - Ensure extraction_status field exists
```

---

### PHASE 7: Modify Upload Endpoints
**File:** `api/form.py`

**POST `/form/personal-document/upload`:**
1. Validate file format
2. Save file to disk
3. Save document path to workers table
4. Set personal_extraction_status = 'pending'
5. Return immediately (no OCR yet)

**POST `/form/educational-document/upload`:**
1. Validate file format
2. Save file to disk
3. Create/save record in educational_documents table
4. Set extraction_status = 'pending'
5. Return immediately (no OCR yet)

---

### PHASE 8: Enhance GET Worker Data Endpoint
**File:** `api/form.py`

**GET `/form/worker/{worker_id}/data`:**
1. Fetch worker record
2. Check for pending personal documents (extraction_status = 'pending')
3. Check for pending educational documents (extraction_status = 'pending')
4. **ALWAYS trigger background processing for any pending documents**
5. Return response with:
   - Current extracted data (if already processed)
   - processing_status field
   - Message indicating if data is being processed

**Response Structure:**
```json
{
  "status": "success",
  "worker": {
    "worker_id": "...",
    "name": "BABU KHAN",  // null if still processing
    "dob": "01-12-1987",   // null if still processing
    "address": "...",      // null if still processing
    "mobile_number": "..."
  },
  "education": [
    {
      "id": "...",
      "extraction_status": "completed",  // or "pending"
      "document_type": "marksheet",
      "qualification": "Class 10",
      "board": "CBSE",
      "stream": "Science",
      "year_of_passing": "2017",
      "school_name": "ST DON BOSCO COLLEGE",
      "marks_type": "CGPA",
      "marks": "07.4"
    }
  ],
  "has_experience": false,
  "has_cv": false,
  "processing_status": "processing"  // or "completed"
}
```

---

## Flow Diagram

```
1. User uploads personal/educational document
   ↓
2. Upload endpoint saves file → returns immediately
   ↓
3. User calls GET /form/worker/{worker_id}/data
   ↓
4. GET endpoint checks for pending documents
   ├─ YES: Trigger background processing jobs
   └─ NO: Skip
   ↓
5. Return response with current data + processing_status
   ↓
6. Background processing runs async:
   - Extract OCR from document
   - Call LLM to parse OCR text
   - Update database with extracted data
   - Mark as 'completed'
   ↓
7. Next GET call returns complete extracted data
```

---

## Implementation Checklist

- [ ] Phase 1: Create `services/llm_document_extractor.py`
- [ ] Phase 2: Enhance `services/ocr_service.py`
- [ ] Phase 3: Create `services/background_processor.py`
- [ ] Phase 4: Update `db/crud.py` with new functions
- [ ] Phase 5: Create database migrations
- [ ] Phase 6: Update `db/models.py`
- [ ] Phase 7: Simplify upload endpoints
- [ ] Phase 8: Enhance GET endpoint with always-fetch logic
- [ ] Testing: Verify all extraction flows work correctly

---

## Key Features

✅ Documents uploaded immediately (no processing delay)
✅ Background processing triggered on every GET call
✅ OCR with PDF-to-image fallback built-in
✅ LLM-powered structured extraction
✅ Clear processing status indicators
✅ Data persists to database immediately after processing

