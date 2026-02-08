# Implementation Decision Checklist

Before starting implementation, please review and approve all decisions:

---

## PHASE 1: DATABASE SCHEMA

### Decision 1.1: Workers Table Verification Fields
**Question:** Add verification columns to workers table?
- ✅ **RECOMMENDED:** YES - Enables verification status tracking at worker level
- Impact: 4 new columns (verification_status, verified_at, verification_errors, last_verified_document_set)
- Breaking: No - all columns nullable, backward compatible
- **APPROVE:** ☐ YES ☐ NO ☐ MODIFY

### Decision 1.2: Educational Documents Metadata
**Question:** Add extraction metadata to educational_documents table?
- ✅ **RECOMMENDED:** YES - Stores LLM extraction results, confidence scores, and raw OCR
- Impact: 9 new columns (document_class, raw_ocr_text, marks_data, calculated_percentage, extracted_name, extracted_dob, extracted_address, verification_flag, confidence_scores)
- Breaking: No - all columns nullable
- **APPROVE:** ☐ YES ☐ NO ☐ MODIFY

### Decision 1.3: Verification Log Table
**Question:** Create audit log table for verification comparisons?
- ✅ **RECOMMENDED:** YES - Essential for compliance and debugging verification mismatches
- Impact: New table with 11 columns
- Breaking: No - new table only
- **APPROVE:** ☐ YES ☐ NO ☐ MODIFY

---

## PHASE 2: NEW SERVICES

### Decision 2.1: Document Processor Service
**Question:** Create dedicated service for document format handling?
- ✅ **RECOMMENDED:** YES - Separates concerns, handles camera capture conversion, multi-format support
- Location: `services/document_processor.py`
- Functions: 5 core functions + helpers
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

### Decision 2.2: LLM Document Extractor Service
**Question:** Create LLM-powered extraction service with confidence scoring?
- ✅ **RECOMMENDED:** YES - Structured data extraction with confidence scores
- Location: `services/llm_document_extractor.py`
- LLM: OpenAI GPT-4 (configured via LLM_API_KEY env var)
- Functions: 6 core functions (personal, 10th, 12th extraction + helpers)
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

### Decision 2.3: Document Verifier Service
**Question:** Create verification service with fuzzy matching?
- ✅ **RECOMMENDED:** YES - Compare extracted data across documents with detailed reporting
- Location: `services/document_verifier.py`
- Fuzzy match threshold: 85% (Levenshtein distance)
- DOB matching: Exact only
- Functions: 5 core functions
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

### Decision 2.4: Background Jobs Service
**Question:** Create async job queue service?
- ✅ **RECOMMENDED:** YES - Essential for non-blocking upload, prevents API timeouts
- Location: `services/background_jobs.py`
- Mechanism: In-memory queue with status tracking (can upgrade to Redis/Celery later)
- Functions: 6 core functions
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

---

## PHASE 3: OCR SERVICE ENHANCEMENT

### Decision 3.1: PDF Support
**Question:** Add PDF text extraction + OCR to ocr_service.py?
- ✅ **RECOMMENDED:** YES - Many users submit PDFs; need both native text extraction + OCR for scanned
- Library: pdfplumber for native PDFs
- Fallback: PaddleOCR for scanned PDFs
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

### Decision 3.2: Multi-Format Routing
**Question:** Add file format detection and routing?
- ✅ **RECOMMENDED:** YES - Route PDFs to PDF handler, images to image OCR
- Breaking: No - only adds new functions, existing code unchanged
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

---

## PHASE 4: CRUD OPERATIONS

### Decision 4.1: New CRUD Functions
**Question:** Add 6 new CRUD functions for verification workflow?
- ✅ **RECOMMENDED:** YES - Required for extraction and verification metadata storage
- Functions:
  1. `save_document_with_extraction()` - Save OCR + LLM results
  2. `get_document_extraction_status()` - Check extraction progress
  3. `update_verification_status()` - Update worker verification
  4. `save_verification_log()` - Create audit log
  5. `get_all_worker_documents_for_verification()` - Get docs for verification
  6. `get_verification_status()` - Get verification details
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

### Decision 4.2: Modify Existing CRUD Functions
**Question:** Modify existing functions to support new metadata?
- ✅ **RECOMMENDED:** YES - update_worker_data(), save_educational_document() need confidence/class
- Breaking: No - new parameters optional
- Impact: 3 functions affected
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

---

## PHASE 5: API ENDPOINT REFACTORING

### Decision 5.1: Personal Upload Endpoint
**Question:** Refactor POST /form/personal/upload for async + camera?
- ✅ **RECOMMENDED:** YES - Support camera capture, return immediately with upload_id
- Changes:
  - Add `upload_type` parameter (file/camera)
  - Add `camera_data` parameter (base64)
  - Return 200 immediately (not after OCR)
  - Trigger background job
  - Return upload_id for status polling
- Breaking: Slightly - response format changes
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

### Decision 5.2: Educational Upload Endpoint
**Question:** Refactor POST /form/educational/upload for multi-file + classification?
- ✅ **RECOMMENDED:** YES - Support multiple files, classify as 10th/12th, camera support
- Changes:
  - Add `upload_type` parameter
  - Add `camera_data` array
  - Add `document_class` array (map files to classes)
  - Support `files` array (multiple files)
  - Return array of upload_ids
- Breaking: Significantly - signature changes
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

### Decision 5.3: Worker Data Retrieval Endpoint
**Question:** Enhance GET /form/worker/{id}/data with verification + job status?
- ✅ **RECOMMENDED:** YES - Essential for workflow: check status → retrieve data → show verification
- Changes:
  - Add query params: include_verification, include_raw_ocr, wait_for_processing
  - Return 202 if processing (with job status)
  - Return 400 if verification failed (with mismatches)
  - Return 200 with full data + verification on success
  - Display both percentage and calculated_percentage
- Breaking: Yes - response format significantly enhanced
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

### Decision 5.4: Response Format Standardization
**Question:** Standardize ALL endpoints to {statusCode, responseData} format?
- ✅ **RECOMMENDED:** YES - Critical for frontend consistency
- Format:
  ```json
  {
    "statusCode": 200|201|202|400|500,
    "responseData": {
      "message": "...",
      "data": {},
      "errors": []
    }
  }
  ```
- Affected endpoints:
  - POST /form/signup
  - POST /form/submit (if exists)
  - All CV endpoints
  - All experience endpoints
  - GET /form/worker/{id}
  - Plus new/modified endpoints above
- Breaking: Yes - all endpoints change format
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

---

## PHASE 6: CONFIGURATION & ENVIRONMENT

### Decision 6.1: Environment Variables
**Question:** Use environment variables for LLM, verification thresholds, timeouts?
- ✅ **RECOMMENDED:** YES - Makes service configurable without code changes
- Variables:
  - LLM_API_KEY, LLM_MODEL, LLM_TEMPERATURE
  - VERIFICATION_NAME_THRESHOLD, VERIFICATION_DOB_EXACT
  - JOB_TIMEOUT_SECONDS, JOB_RETRY_ATTEMPTS
  - MAX_FILE_SIZE_MB, SUPPORTED_FORMATS
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

### Decision 6.2: Required Dependencies
**Question:** Add new Python packages?
- ✅ **RECOMMENDED:** YES
- Packages:
  - pdfplumber (PDF extraction)
  - python-Levenshtein (fuzzy matching)
  - openai (already likely present)
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

---

## IMPLEMENTATION DETAILS

### Decision 7.1: Fuzzy Name Matching Threshold
**Question:** Set name matching threshold to 85%?
- ✅ **RECOMMENDED:** YES - Balances false positives (too low) vs false negatives (too high)
- Examples:
  - "BABU KHAN" vs "BABU KHANN" → 95% match → PASS
  - "BABU KHAN" vs "BABUU KHAN" → 86% match → PASS
  - "BABU KHAN" vs "RAM KUMAR" → 0% match → FAIL
- Customizable: YES - via VERIFICATION_NAME_THRESHOLD env var
- **APPROVE:** ☐ YES ☐ NO ☐ MODIFY (specify threshold: ___)

### Decision 7.2: DOB Verification
**Question:** Require EXACT DOB match (no fuzzy)?
- ✅ **RECOMMENDED:** YES - DOB is unique identifier, any mismatch = document mismatch
- Format: YYYY-MM-DD
- Customizable: YES - via VERIFICATION_DOB_EXACT env var
- **APPROVE:** ☐ YES ☐ NO ☐ MODIFY

### Decision 7.3: Job Retry Strategy
**Question:** Retry failed jobs up to 3 times with exponential backoff?
- ✅ **RECOMMENDED:** YES - Handles transient OCR/LLM failures
- Retry count: 3
- Backoff: Exponential (5s, 10s, 20s)
- Customizable: YES - via JOB_RETRY_ATTEMPTS env var
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

### Decision 7.4: Background Processing
**Question:** Use in-memory job queue or upgrade to Redis/Celery later?
- ✅ **RECOMMENDED:** Start with in-memory for POC, upgrade to Redis/Celery later
- Mechanism: In-memory dict with job status
- Limitation: Jobs lost on server restart
- Future: Can migrate to Celery/Redis without API changes
- **APPROVE:** ☐ YES ☐ NO ☐ USE_CELERY

---

## TESTING & VALIDATION

### Decision 8.1: Test Coverage
**Question:** Test all new services and endpoints?
- ✅ **RECOMMENDED:** YES - Create test suite
- Coverage:
  - Document processor (format validation, camera conversion)
  - LLM extractor (with mock LLM responses)
  - Verifier (fuzzy matching, comparison logic)
  - Background jobs (status tracking, retries)
  - API endpoints (all status codes, error cases)
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

### Decision 8.2: Backward Compatibility
**Question:** Maintain backward compatibility with existing endpoints?
- ✅ **RECOMMENDED:** YES - If possible, but new endpoints may break existing clients
- Approach:
  - New endpoints: POST /form/personal/upload, POST /form/educational/upload
  - Enhanced endpoint: GET /form/worker/{id}/data (may break client if response format not handled)
  - Keep old endpoints if clients depend on them
- **APPROVE:** ☐ YES ☐ NO ☐ MODIFY

---

## DEPLOYMENT & MONITORING

### Decision 9.1: Monitoring
**Question:** Add logging for all background jobs?
- ✅ **RECOMMENDED:** YES - Critical for debugging extraction/verification failures
- Log points:
  - Job created, processing started, completed, failed
  - OCR results (raw text length, confidence)
  - LLM API calls (tokens, response time)
  - Verification comparisons (all pairs, mismatches)
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

### Decision 9.2: Error Recovery
**Question:** Implement graceful error recovery?
- ✅ **RECOMMENDED:** YES
- Strategy:
  - If OCR fails: Save raw file, mark job failed, user can retry
  - If LLM fails: Retry with backoff, then mark failed
  - If verification fails: Show mismatches to user
  - No silent failures: All errors logged and surfaced
- **APPROVE:** ☐ YES ☐ NO ☐ SKIP

---

## SUMMARY

### What Gets Created
- 4 new service files
- 1 modified service file
- 1 modified database module
- 1 modified CRUD module
- 1 modified API module
- 1 modified models module
- 3 comprehensive documentation files

### What Gets Modified
- workers table schema
- educational_documents schema
- ocr_service.py (enhanced)
- crud.py (6 new functions)
- form.py (3 endpoints refactored)
- models.py (new response models)

### Breaking Changes
- Response format standardization (all endpoints)
- Personal upload endpoint signature change
- Educational upload endpoint signature change
- Worker data endpoint response structure change

### Backward Compatibility
- Database: Fully backward compatible (new columns nullable)
- Existing code: Will need migration for API consumers
- Data: No data loss, all existing data preserved

### Migration Path
1. Deploy new database schema
2. Deploy new services
3. Gradually migrate endpoints (can run old + new in parallel)
4. Update clients to use new response format
5. Deprecate old endpoints after client migration

---

## FINAL CHECKLIST

Before implementation starts, confirm:

- [ ] I understand the new service architecture
- [ ] I approve all 4 new services (document_processor, llm_extractor, verifier, background_jobs)
- [ ] I approve PDF support in OCR service
- [ ] I approve 6 new CRUD functions
- [ ] I approve refactoring of 3 main endpoints
- [ ] I approve response format standardization
- [ ] I approve fuzzy name matching threshold (85%)
- [ ] I approve exact DOB matching
- [ ] I approve in-memory job queue (upgradeable to Celery later)
- [ ] I approve 3 times retry with exponential backoff
- [ ] I have LLM_API_KEY configured (for GPT-4 access)
- [ ] I understand breaking changes to API format
- [ ] I understand database schema additions are backward compatible
- [ ] I'm ready for implementation to start

---

## NEXT STEPS

Once all checkboxes above are confirmed:

1. **Immediate:** Run database migrations
2. **Day 1-2:** Create new services layer
3. **Day 2-3:** Enhance OCR and update CRUD
4. **Day 4:** Refactor API endpoints
5. **Day 5:** Integration testing
6. **Day 6:** Deployment and validation

**Expected Timeline:** 1 week for full implementation
**Expected Code Quality:** Production-ready with proper error handling, logging, and documentation

---

**Please review, approve all decisions above, and confirm you're ready to proceed with implementation.**

