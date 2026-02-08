# CV POC - New Services Implementation Workflow

## Overview
This document outlines the complete workflow for implementing new LLM-based document extraction and verification services into the existing CV POC backend.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    API LAYER (3 Main Endpoints)                    │
├─────────────────────────────────────────────────────────────────────┤
│ • POST /form/personal/upload      - Personal doc upload             │
│ • POST /form/educational/upload   - Educational docs upload         │
│ • GET /form/worker/{id}/data      - Retrieve & verify all data     │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────────────┐
│              BACKGROUND PROCESSING (Async Jobs)                     │
├─────────────────────────────────────────────────────────────────────┤
│ OCR Job Flow:                                                       │
│   1. Document Processor → Validate & convert formats               │
│   2. OCR Service → Extract raw text                                │
│   3. LLM Document Extractor → Parse structured data + confidence  │
│   4. Save to DB with extraction metadata                           │
│                                                                     │
│ Verification Job Flow:                                             │
│   1. Document Verifier → Compare all document pairs                │
│   2. Fuzzy match names, exact match DOBs                          │
│   3. Update workers table with verification status                │
│   4. Create verification log entries                               │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────────────┐
│              SERVICES LAYER (Core Business Logic)                   │
├─────────────────────────────────────────────────────────────────────┤
│ [NEW] services/document_processor.py                                │
│   - Validate formats (PDF, JPG, PNG)                               │
│   - Handle camera captures (base64 conversion)                     │
│   - Route to appropriate OCR engine                                │
│                                                                     │
│ [NEW] services/llm_document_extractor.py                           │
│   - Extract personal data (name, DOB, address, mobile)            │
│   - Extract 10th marksheet data (marks, percentage, board)        │
│   - Extract 12th marksheet data (marks, CGPA/percentage)          │
│   - Calculate percentages from marks                               │
│   - Generate confidence scores for each field                      │
│                                                                     │
│ [NEW] services/document_verifier.py                                │
│   - Fuzzy name matching (Levenshtein distance)                    │
│   - Exact DOB/address matching                                     │
│   - Multi-document comparison (personal vs 10th, etc.)            │
│   - Generate detailed mismatch reports                             │
│                                                                     │
│ [NEW] services/background_jobs.py                                  │
│   - Manage OCR/LLM job queue                                      │
│   - Track job status (pending → processing → completed)           │
│   - Handle retries and error recovery                              │
│                                                                     │
│ [MODIFIED] services/ocr_service.py                                │
│   - Add PDF support (pdfplumber + OCR fallback)                   │
│   - Keep existing image OCR (PaddleOCR/Tesseract)                │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────────────┐
│              CRUD LAYER (Database Operations)                       │
├─────────────────────────────────────────────────────────────────────┤
│ [NEW FUNCTIONS] db/crud.py                                          │
│   - save_document_with_extraction()                                │
│   - get_document_extraction_status()                               │
│   - update_verification_status()                                   │
│   - save_verification_log()                                        │
│   - get_all_worker_documents_for_verification()                   │
│   - get_verification_status()                                      │
│                                                                     │
│ [MODIFIED FUNCTIONS]                                              │
│   - update_worker_data() → Add confidence scores                   │
│   - save_educational_document() → Add extraction metadata          │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────────────┐
│              DATABASE LAYER (SQLite)                                │
├─────────────────────────────────────────────────────────────────────┤
│ [MODIFIED] workers table                                            │
│   + verification_status (verified, pending, failed)                │
│   + verified_at (timestamp)                                         │
│   + verification_errors (JSON with mismatches)                     │
│   + last_verified_document_set                                     │
│                                                                     │
│ [MODIFIED] educational_documents table                             │
│   + document_class ('10th', '12th', 'other')                      │
│   + raw_ocr_text (raw extraction before LLM)                      │
│   + marks_data (JSON: {subject: marks})                           │
│   + calculated_percentage (auto-calc for 12th)                    │
│   + extracted_name, extracted_dob, extracted_address              │
│   + verification_flag (verified, pending, failed)                 │
│   + confidence_scores (JSON: {name: 0.95, dob: 0.98})            │
│                                                                     │
│ [NEW] document_verification_log table                              │
│   - Track all verification comparisons                             │
│   - Store detailed mismatch information                            │
│   - Enable verification audit trail                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagrams

### Upload Flow

```
USER UPLOADS DOCUMENT
    │
    ▼
POST /form/personal/upload (or educational)
    │
    ├─ Validate file format
    ├─ Convert camera data if needed
    ├─ Save to disk
    └─ Return {statusCode: 200, responseData: {upload_id, processing_status: "queued"}}
    
    ▼ (ASYNC - Background Job)
    
CREATE OCR JOB
    │
    ├─ Call document_processor.extract_raw_text()
    │  └─ Returns raw OCR text
    │
    ├─ Call llm_document_extractor.extract_*_data(raw_text)
    │  ├─ Parse JSON response
    │  ├─ Calculate confidence scores
    │  └─ Returns {extracted_data, confidence_scores}
    │
    └─ Call crud.save_document_with_extraction()
       └─ Save to DB with all metadata
```

### Data Retrieval & Verification Flow

```
GET /form/worker/{worker_id}/data (include_verification=true)
    │
    ├─ Check job status
    │  ├─ If processing: Return 202 with progress
    │  └─ If complete: Continue...
    │
    ├─ Get personal document data
    ├─ Get all educational documents (10th, 12th, etc.)
    │
    ├─ Call document_verifier.compare_documents([personal, 10th, 12th])
    │  ├─ Compare all pairs:
    │  │  ├─ personal vs 10th (name, DOB, address)
    │  │  ├─ personal vs 12th (name, DOB, address)
    │  │  └─ 10th vs 12th (name, DOB)
    │  │
    │  └─ Returns {matches, mismatches, verification_status}
    │
    ├─ Update verification_status in DB
    │
    └─ Return 200 with:
       ├─ Personal data + extraction metadata
       ├─ All education data with calculations
       └─ Verification results
```

---

## Response Format Standards

### Success Response (200)

```json
{
  "statusCode": 200,
  "responseData": {
    "message": "Operation successful",
    "data": { /* operation-specific data */ }
  }
}
```

### Processing Response (202)

```json
{
  "statusCode": 202,
  "responseData": {
    "message": "Processing in progress",
    "processing_status": "processing",
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

### Error Response (400/500)

```json
{
  "statusCode": 400,
  "responseData": {
    "message": "Operation failed",
    "errors": [
      {
        "type": "error_type",
        "field": "field_name",
        "message": "Error description"
      }
    ]
  }
}
```

---

## LLM Extraction Prompts

### Personal Document Extraction

```
Extract from the following OCR text: name, date of birth (in YYYY-MM-DD format), 
address, and mobile number.

Return a JSON response with:
{
  "name": "extracted name",
  "dob": "YYYY-MM-DD",
  "address": "extracted address",
  "mobile": "phone number",
  "confidence": {
    "name": 0.95,
    "dob": 0.98,
    "address": 0.92,
    "mobile": 0.97
  }
}

Only include fields you can confidently extract. If unsure, set confidence < 0.8.
```

### 10th Marksheet Extraction

```
This is a 10th class marksheet. Extract:
- class (10th)
- board name (CBSE, State Board, etc.)
- marks by subject
- total marks obtained
- total maximum possible marks
- percentage (if shown; otherwise calculate)

Return JSON:
{
  "class": "10th",
  "board": "CBSE",
  "marks": {
    "subject1": 85,
    "subject2": 78,
    ...
  },
  "total_obtained": 420,
  "total_possible": 500,
  "percentage": 84.0,
  "confidence": {
    "board": 0.95,
    "marks": 0.92,
    "percentage": 0.99
  }
}
```

### 12th Marksheet Extraction

```
This is a 12th class marksheet. Extract:
- board name
- marks by subject
- total obtained marks
- total maximum possible marks
- Calculate: percentage = (total_obtained / total_possible) * 100

Handle different marking systems:
- CBSE: 100 per subject
- State boards: Vary

Return JSON:
{
  "board": "CBSE",
  "marks": {
    "math": 88,
    "english": 85,
    ...
  },
  "total_obtained": 430,
  "total_possible": 500,
  "calculated_percentage": 86.0,
  "confidence": {
    "marks": 0.93,
    "percentage": 0.99
  }
}
```

---

## Implementation Phases

### Phase 1: Database Schema Updates
- Add verification columns to workers table
- Add extraction metadata to educational_documents
- Create document_verification_log table

### Phase 2: Create New Services
- `document_processor.py` - Format validation & conversion
- `llm_document_extractor.py` - Structured data extraction
- `document_verifier.py` - Cross-document verification
- `background_jobs.py` - Job queue management

### Phase 3: Enhance OCR Service
- Add PDF support with pdfplumber
- Keep existing image OCR logic
- Add format detection

### Phase 4: Update CRUD Layer
- Add new verification functions
- Modify existing functions for metadata
- Add extraction status tracking

### Phase 5: Refactor API Endpoints
- Modify personal upload endpoint
- Modify educational upload endpoint
- Enhance worker data retrieval endpoint
- Standardize all response formats

### Phase 6: Integration Testing
- Test complete upload → extraction → verification flow
- Test error scenarios
- Test background job status retrieval

---

## Error Handling Strategy

### Document Upload Errors
- Invalid format: Return 400 with validation error
- File too large: Return 413
- Disk space: Return 507

### OCR Errors
- PaddleOCR/Tesseract failure: Log and retry
- PDF parsing failure: Fall back to image conversion
- No text detected: Mark as failed, save raw text for manual review

### LLM Extraction Errors
- API timeout: Retry with exponential backoff
- Invalid JSON: Parse failure, save raw extraction
- Low confidence: Flag for manual review

### Verification Errors
- Missing documents: Partial verification (e.g., personal vs 10th only)
- Name mismatch: Store details in mismatch_details JSON
- DOB mismatch: Mark verification failed

---

## Configuration & Environment Variables

Required environment variables:
```
LLM_API_KEY=<openai-api-key>
LLM_MODEL=gpt-4
VERIFICATION_NAME_THRESHOLD=0.85  # Fuzzy match threshold
VERIFICATION_DOB_EXACT=true       # DOB must match exactly
```

---

## Testing Checklist

- [ ] Database migrations execute without errors
- [ ] Document processor handles all file formats
- [ ] Camera capture (base64) converts correctly
- [ ] OCR extracts text from PDFs and images
- [ ] LLM extraction returns valid JSON
- [ ] Confidence scores calculated correctly
- [ ] Percentage calculation handles different boards
- [ ] Fuzzy name matching works (threshold 85%)
- [ ] Verification compares all document pairs
- [ ] Background jobs track status correctly
- [ ] 202 response returns proper job status
- [ ] 400 response shows detailed mismatches
- [ ] All endpoints return standardized format
- [ ] Error messages are user-friendly

---

## Success Criteria

1. All endpoints use new services in background
2. LLM extracts structured data with confidence scores
3. Percentage/CGPA displayed for both 10th and 12th
4. Verification compares all document pairs
5. All responses follow standardized format
6. No code is broken
7. Background processing handles async operations
8. Detailed audit logs for all verifications

