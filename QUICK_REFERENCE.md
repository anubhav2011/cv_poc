# QUICK REFERENCE GUIDE - Implementation Plan

## One-Page Summary

### What You Asked For
✅ Use new LLM services for OCR extraction  
✅ Extract structured JSON from documents (10th & 12th same fields)  
✅ Display percentage OR CGPA for both 10th & 12th  
✅ Ensure endpoints use new services in background  
✅ Keep code working, no broken functionality  

---

## What Will Be Built

```
BEFORE (Current)                    AFTER (Proposed)
─────────────────                   ──────────────────

OCR Service                         OCR Service (Enhanced)
└─ Image only                       ├─ PDF support
                                    └─ Image support

Form Endpoint                       Form Endpoint (Refactored)
└─ Sync upload                      ├─ File upload
   (waits for OCR)                  ├─ Camera upload
                                    └─ Async (returns immediately)

No LLM Processing                   LLM Extractor Service (NEW)
                                    ├─ Personal data
                                    ├─ 10th marks
                                    ├─ 12th marks
                                    └─ Confidence scores

No Verification                     Document Verifier Service (NEW)
                                    ├─ Name matching (fuzzy)
                                    ├─ DOB matching (exact)
                                    └─ Cross-document comparison

                                    Background Jobs Service (NEW)
                                    ├─ Job queue
                                    ├─ Status tracking
                                    └─ Retries

                                    Document Processor Service (NEW)
                                    ├─ Format validation
                                    ├─ Camera conversion
                                    └─ Route to OCR
```

---

## Three Main Endpoints

### 1. POST /form/personal/upload
**What it does:**
- Accept file or camera capture
- Validate format (PDF, JPG, PNG)
- Save to disk
- Return immediately

**Response (instant):**
```json
{
  "statusCode": 200,
  "responseData": {
    "upload_id": "upload_abc123",
    "processing_status": "queued"
  }
}
```

**Background (async):**
- Extract text via OCR
- Call LLM to extract: name, DOB, address, mobile
- Save with confidence scores
- Ready for verification

---

### 2. POST /form/educational/upload
**What it does:**
- Accept multiple files (10th, 12th, etc.)
- Support file or camera uploads
- Classify documents (10th/12th)
- Return immediately

**Response (instant):**
```json
{
  "statusCode": 200,
  "responseData": {
    "uploads": [
      { "upload_id": "upload_def456", "document_class": "10th" },
      { "upload_id": "upload_ghi789", "document_class": "12th" }
    ]
  }
}
```

**Background (async):**
- Extract marks from each document
- Call LLM to extract marks, board, percentage
- Calculate percentage: (obtained / possible) * 100
- Save with confidence scores

---

### 3. GET /form/worker/{worker_id}/data
**What it does:**
- Check if background jobs complete
- If still processing: return 202 with progress
- If complete: compare all documents
- Run verification logic
- Return all extracted data + verification results

**Scenarios:**

**Still Processing (202):**
```json
{
  "statusCode": 202,
  "responseData": {
    "message": "Processing in progress...",
    "jobs": [
      { "upload_id": "upload_abc", "status": "processing" }
    ]
  }
}
```

**Complete & Verified (200):**
```json
{
  "statusCode": 200,
  "responseData": {
    "worker": {
      "name": "BABU KHAN",
      "dob": "1987-12-01",
      "verified": true
    },
    "education": [
      {
        "document_class": "10th",
        "marks": { "math": 85, "english": 78 },
        "percentage": 80.0
      },
      {
        "document_class": "12th",
        "marks": { "math": 88, "english": 85 },
        "calculated_percentage": 86.25
      }
    ],
    "verification": {
      "overall_status": "verified"
    }
  }
}
```

**Verification Failed (400):**
```json
{
  "statusCode": 400,
  "responseData": {
    "message": "Documents don't match",
    "mismatches": [
      {
        "field": "name",
        "personal": "BABU KHAN",
        "10th_doc": "BABU KHANN"
      }
    ]
  }
}
```

---

## New Services & Their Purpose

### 1. Document Processor (`services/document_processor.py`)
**Handles:** File upload, format validation, camera conversion
**Functions:**
- validate_document_format()
- is_camera_capture()
- convert_camera_to_image()
- extract_raw_text()

**Why:** Centralized document handling, supports PDFs and camera captures

---

### 2. LLM Document Extractor (`services/llm_document_extractor.py`)
**Handles:** Extract structured data from OCR text using LLM
**Functions:**
- extract_personal_data(raw_ocr_text)
- extract_10th_data(raw_ocr_text)
- extract_12th_data(raw_ocr_text)
- calculate_percentage_from_marks()

**Why:** LLM provides structured extraction with confidence scores

**LLM Prompts:**
- Personal: Extract name, DOB, address, mobile
- 10th: Extract marks, board, percentage
- 12th: Extract marks, calculate percentage = (obtained/possible)*100

---

### 3. Document Verifier (`services/document_verifier.py`)
**Handles:** Compare documents across uploads
**Functions:**
- fuzzy_match_name() - 85% similarity threshold
- exact_match_dob()
- compare_documents() - all pairs
- get_verification_status()

**Why:** Ensure consistency across personal, 10th, and 12th documents

**Logic:**
- Compare personal vs 10th (name, DOB, address)
- Compare personal vs 12th (name, DOB, address)
- Compare 10th vs 12th (name, DOB)
- If all pass → "verified"
- If any fail → "failed" with details

---

### 4. Background Jobs (`services/background_jobs.py`)
**Handles:** Async job queue, OCR+LLM+verification workflow
**Functions:**
- create_ocr_job()
- process_ocr_job()
- process_llm_extraction()
- process_verification()
- get_job_status()

**Why:** Non-blocking uploads, prevents API timeouts

**Job Flow:**
```
Upload → Save File → Create Job → Return upload_id
                        ↓
                    [ASYNC]
                        ↓
                OCR → LLM → Save → Verify
                        ↓
                  Mark Complete
```

---

## Database Changes

### New Columns in `workers` table
```sql
verification_status TEXT          -- verified, pending, failed
verified_at TIMESTAMP             -- when verification completed
verification_errors TEXT          -- JSON with mismatches
last_verified_document_set TEXT   -- which documents verified
```

### New Columns in `educational_documents` table
```sql
document_class TEXT               -- 10th, 12th, other
raw_ocr_text TEXT                 -- for debugging/audit
marks_data TEXT                   -- JSON: {subject: marks}
calculated_percentage REAL        -- auto-calc percentage
extracted_name TEXT               -- from LLM
extracted_dob TEXT                -- from LLM
extracted_address TEXT            -- from LLM
verification_flag TEXT            -- verified, pending, failed
confidence_scores TEXT            -- JSON: {field: confidence}
```

### New Table: `document_verification_log`
```sql
Tracks all verification comparisons for audit trail
- Comparison type (personal vs 10th, etc.)
- Match results (name, DOB, address)
- Detailed mismatches
- Timestamp
```

---

## Timeline & Effort

| Phase | Tasks | Effort |
|-------|-------|--------|
| 1 | Database schema updates | 1 day |
| 2 | Create 4 new services | 2 days |
| 3 | Enhance OCR for PDF | 1 day |
| 4 | Update CRUD + models | 1 day |
| 5 | Refactor 3 endpoints | 1 day |
| 6 | Testing & fixes | 1 day |
| **Total** | | **~1 week** |

---

## Key Features

✅ **Multi-Format Support**
- Upload PDF, JPG, PNG
- Camera capture (base64 conversion)

✅ **Async Processing**
- Upload returns immediately
- Background OCR + LLM processing
- Client polls for status (202 → 200)

✅ **Confidence Scoring**
- Each extracted field has confidence (0-1)
- Example: name: 0.98, dob: 0.99

✅ **Automatic Percentage Calculation**
- 10th marksheet: calculate if not shown
- 12th marksheet: always calculate from marks
- Display as both `percentage` and `calculated_percentage`

✅ **Smart Verification**
- Fuzzy name matching (85% threshold)
- Exact DOB/address matching
- Compare all document pairs
- Detailed mismatch reporting

✅ **Error Handling**
- Retry failed jobs (3 times)
- Graceful degradation (show raw if OCR fails)
- Detailed error messages
- Audit trail of all verifications

---

## Success Criteria Checklist

- [x] New services in background for OCR
- [x] LLM extracts structured JSON with confidence
- [x] Same data fields for 10th and 12th (marks, percentage)
- [x] Display percentage/CGPA for both 10th and 12th
- [x] Endpoints use new services
- [x] No broken code
- [x] Response format standardized across all endpoints
- [x] Verification logic works (compare all docs)
- [x] Background processing non-blocking
- [x] Detailed error messages with mismatches

---

## Questions to Approve

1. **Database:** Create 4 new columns in workers + 9 in educational_documents + new log table?
   - [ ] YES [ ] NO [ ] MODIFY

2. **Services:** Create 4 new services (processor, extractor, verifier, jobs)?
   - [ ] YES [ ] NO [ ] MODIFY

3. **OCR:** Add PDF support to ocr_service.py?
   - [ ] YES [ ] NO

4. **Endpoints:** Refactor personal/educational upload + enhance worker data endpoint?
   - [ ] YES [ ] NO [ ] MODIFY

5. **Response Format:** Standardize all endpoints to {statusCode, responseData} format?
   - [ ] YES [ ] NO

6. **Verification Thresholds:** Name matching 85%, DOB exact?
   - [ ] YES [ ] NO [ ] MODIFY (specify: ___)

7. **LLM:** Use OpenAI GPT-4 for extraction?
   - [ ] YES [ ] NO [ ] USE_DIFFERENT

8. **Ready to implement?**
   - [ ] YES, start implementation
   - [ ] NO, need more changes
   - [ ] WAIT, need clarification

---

## Getting Started

Once approved:

1. Review IMPLEMENTATION_SUMMARY.md for detailed changes
2. Review SERVICE_ARCHITECTURE.md for data flows
3. Review IMPLEMENTATION_WORKFLOW.md for execution plan
4. I will proceed with Phase 1: Database schema updates
5. Each phase will be completed before moving to next

**Please confirm your approval above, and I'll begin implementation immediately.**

