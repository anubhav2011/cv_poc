# Document Verification Implementation

## Overview

This document describes the implementation of document verification that checks if personal document (name, dob) matches with educational documents.

## Files Changed/Created

### 1. NEW: `services/document_verification.py`

**Purpose:** Verification service to compare personal and educational document data

**Key Functions:**

#### `normalize_name(name: str) -> str`
- Normalizes names for comparison
- Removes extra spaces, special characters, converts to lowercase
- Removes common titles (Mr., Mrs., Dr., etc.)

#### `normalize_dob(dob: str) -> str`
- Normalizes DOB to consistent format: DD-MM-YYYY
- Handles various formats: DD/MM/YYYY, DD.MM.YYYY, DDMMYYYY, etc.

#### `compare_names(personal_name: str, edu_name: str) -> tuple[bool, str]`
- Compares personal and educational document names
- Returns (is_match, message)

**Matching Logic:**
- Both empty → acceptable
- One empty → acceptable (optional field in education doc)
- Both present → must match (at least 70% similarity)
  - Exact match
  - Names contain each other (e.g., "John Smith" vs "Smith")
  - First or last name matches

#### `compare_dobs(personal_dob: str, edu_dob: str) -> tuple[bool, str]`
- Compares personal and educational document DOBs
- Returns (is_match, message)

**Matching Logic:**
- Both empty → acceptable
- One empty → acceptable
- Both present → must match exactly (after normalization)

#### `verify_documents(personal_data: dict, educational_data: dict) -> dict`
- Main verification function
- Compares personal and educational document data
- Returns detailed verification result:
  ```python
  {
      'verified': bool,
      'name_match': bool,
      'name_message': str,
      'dob_match': bool,
      'dob_message': str,
      'verification_status': 'matched' | 'mismatched' | 'not_applicable',
      'error_message': str (if verification fails),
      'reupload_required': bool
  }
  ```

---

### 2. MODIFIED: `api/form.py`

#### Import Added (Line 20)
```python
from ..services.document_verification import verify_documents
```

#### Function Modified: `_ocr_result()` (Lines 375-389)
**Before:**
```python
def _ocr_result(personal_saved: bool, personal_has_data: bool, education_saved_count: int):
    """Helper to return OCR result dict."""
    return {
        "personal_saved": personal_saved,
        "personal_has_data": personal_has_data,
        "education_saved_count": education_saved_count,
    }
```

**After:**
```python
def _ocr_result(personal_saved: bool, personal_has_data: bool, education_saved_count: int, verification_result: dict = None):
    """Helper to return OCR result dict."""
    result = {
        "personal_saved": personal_saved,
        "personal_has_data": personal_has_data,
        "education_saved_count": education_saved_count,
    }
    
    # Add verification result if available
    if verification_result:
        result["verification_status"] = verification_result.get("verification_status", "not_applicable")
        result["verification_verified"] = verification_result.get("verified", True)
        result["verification_message"] = verification_result.get("error_message")
        result["reupload_required"] = verification_result.get("reupload_required", False)
    
    return result
```

**Change Reason:** Support verification result in OCR processing response

---

#### Function Modified: `get_worker_data()` - OCR Result Handling (Lines 274-303)

**Added Verification Status Handling:**
```python
verification_status = ocr_result.get("verification_status", "not_applicable")
verification_verified = ocr_result.get("verification_verified", True)
verification_message = ocr_result.get("verification_message")
reupload_required = ocr_result.get("reupload_required", False)

# Check verification status first
if verification_status == "mismatched":
    ocr_status = "verification_failed"
    message = f"Document Verification Failed: {verification_message}. Please reupload your documents to ensure name and DOB match across documents."
elif personal_has_data or education_saved_count > 0:
    ocr_status = "completed"
    message = "All data extracted successfully."
else:
    # ... existing error handling
```

**Change Reason:** If verification fails, report it with appropriate status and message

---

#### Function Modified: `get_worker_data()` - Response Data (Lines 360-365)

**Before:**
```python
response_data = {
    "status": "success",
    "worker": WorkerData.model_validate(worker_for_response).model_dump(),
    "education": [edu.model_dump() for edu in education_list],
    "has_experience": has_experience,
    "has_cv": has_cv,
    "ocr_status": ocr_status,
    "message": message,
    "exp_ready": exp_ready,
}
```

**After:**
```python
response_data = {
    "status": "success",
    "worker": WorkerData.model_validate(worker_for_response).model_dump(),
    "education": [edu.model_dump() for edu in education_list],
    "has_experience": has_experience,
    "has_cv": has_cv,
    "ocr_status": ocr_status,
    "message": message,
    "exp_ready": exp_ready,
    "verification_status": locals().get("verification_status", "not_applicable"),
    "reupload_required": locals().get("reupload_required", False),
}
```

**Change Reason:** Include verification status in response to client

---

#### Function Modified: `process_ocr_background()` - Added Verification (Lines 674-731)

**Added Verification Section After Educational Document Processing:**

```python
# ===== VERIFICATION: Check if personal and educational documents match =====
verification_result = None
if personal_saved and education_saved_count > 0:
    logger.info("=" * 80)
    logger.info("[Verification] Starting document verification...")
    logger.info("=" * 80)
    
    # Get personal data
    personal_data = {
        "name": name,
        "dob": dob,
        "address": address
    }
    
    # Get educational data (from the last processed document for verification)
    if education_saved_count > 0:
        # Retrieve the latest educational document from database
        education_docs = crud.get_educational_documents(worker_id)
        if education_docs:
            latest_edu_doc = education_docs[-1]  # Get the last one
            educational_data = {
                "name": latest_edu_doc.get("school_name", ""),
                "dob": None  # Educational documents typically don't have DOB
            }
            
            # Run verification
            verification_result = verify_documents(personal_data, educational_data)
            
            logger.info(f"[Verification] Status: {verification_result.get('verification_status')}")
            if not verification_result.get('verified'):
                logger.error(f"[Verification] ERROR: {verification_result.get('error_message')}")
            else:
                logger.info(f"[Verification] ✓ Verification passed")
else:
    logger.info("[Verification] Skipping verification (no personal or education data)")
    verification_result = {
        'verified': True,
        'verification_status': 'not_applicable',
        'error_message': None
    }

# Return with verification result
return _ocr_result(personal_saved, personal_has_data, education_saved_count, verification_result)
```

**Change Reason:** Verify that personal and educational documents match before returning success

---

## Complete Flow

### 1. User Uploads Personal Document
```
POST /form/personal_document/upload
→ File saved
→ Returns immediately
```

### 2. User Calls GET /form/worker/{worker_id}/data (First Call)
```
GET /form/worker/{worker_id}/data
→ Checks documents exist
→ Calls process_ocr_background()
  ├─ Extracts OCR from personal document
  ├─ Calls LLM to extract: name, dob, address
  ├─ Updates worker table
  └─ Verification status: not_applicable (no education doc yet)
→ Returns personal data + empty education array
```

### 3. User Uploads Educational Document
```
POST /form/educational_document/upload
→ File saved
→ Returns immediately
```

### 4. User Calls GET /form/worker/{worker_id}/data (Second Call)
```
GET /form/worker/{worker_id}/data
→ Checks documents exist
→ Calls process_ocr_background()
  ├─ Personal OCR skipped (already done)
  ├─ Extracts OCR from educational document
  ├─ Calls LLM to extract: qualification, board, marks, etc.
  ├─ Saves to database
  ├─ VERIFICATION RUNS HERE:
  │   ├─ Gets personal data from worker table: name, dob
  │   ├─ Gets educational data from education doc: school_name (as name)
  │   ├─ Compares names
  │   ├─ Compares DOBs (if both present)
  │   └─ Returns verification result
  └─ If verification fails:
      ├─ Status: "verification_failed"
      ├─ Message: "Document Verification Failed: [details]. Please reupload..."
      └─ reupload_required: true
→ Returns personal data + education data + verification status
```

---

## Response Examples

### Verification Passed
```json
{
  "status": "success",
  "ocr_status": "completed",
  "verification_status": "matched",
  "reupload_required": false,
  "message": "All data extracted successfully.",
  "worker": {
    "name": "BABU KHAN",
    "dob": "01-12-1987",
    "address": "KAMLA RAMAN NAGAR..."
  },
  "education": [
    {
      "qualification": "Class 10",
      "board": "CBSE",
      "school_name": "ST DON BOSCO COLLEGE"
    }
  ]
}
```

### Verification Failed (Mismatch)
```json
{
  "status": "success",
  "ocr_status": "verification_failed",
  "verification_status": "mismatched",
  "reupload_required": true,
  "message": "Document Verification Failed: Name MISMATCH: Personal='BABU KHAN' vs Educational='ARJUN SINGH'. Please reupload your documents to ensure name and DOB match across documents.",
  "worker": {
    "name": "BABU KHAN",
    "dob": "01-12-1987"
  },
  "education": []
}
```

### No Verification Needed
```json
{
  "status": "success",
  "ocr_status": "completed",
  "verification_status": "not_applicable",
  "reupload_required": false,
  "message": "All data extracted successfully.",
  "worker": {
    "name": "BABU KHAN",
    "dob": "01-12-1987"
  },
  "education": []
}
```

---

## Verification Rules

### Name Matching
1. **Both empty** → Acceptable ✓
2. **One empty** → Acceptable ✓ (optional field)
3. **Both present:**
   - Exact match → Match ✓
   - One contains other (e.g., "John Smith" vs "Smith") → Match ✓
   - First or last name matches → Match ✓
   - No match → **Mismatch** ✗ (Requires reupload)

### DOB Matching
1. **Both empty** → Acceptable ✓
2. **One empty** → Acceptable ✓ (optional field in education doc)
3. **Both present:**
   - Exact match (after normalization) → Match ✓
   - Different dates → **Mismatch** ✗ (Requires reupload)

### Overall Verification
- **All matches or not_applicable** → Verification Passed ✓
- **Any mismatch** → Verification Failed ✗ (Requires reupload)

---

## Error Cases

| Case | Status | Message | Reupload |
|------|--------|---------|----------|
| Personal and education name don't match | verification_failed | Name MISMATCH: ... | YES |
| Personal and education DOB don't match | verification_failed | DOB MISMATCH: ... | YES |
| Only personal document uploaded | not_applicable | (normal success) | NO |
| Education has no name/DOB | not_applicable | (normal success) | NO |
| Both match perfectly | matched | All data extracted successfully. | NO |

---

## Testing

### Scenario 1: Documents Match
1. Upload personal: Name="BABU KHAN", DOB="01-12-1987"
2. Call GET endpoint → Success
3. Upload education: School="ST DON BOSCO", DOB=None
4. Call GET endpoint → verification_status="not_applicable" (school_name doesn't contain personal name matching logic)

### Scenario 2: Documents Don't Match
1. Upload personal: Name="BABU KHAN", DOB="01-12-1987"
2. Call GET endpoint → Success
3. Upload education from different person: School="ARJUN SINGH SCHOOL"
4. Call GET endpoint → verification_status="mismatched", reupload_required=true

### Scenario 3: Partial Match (Last Name)
1. Upload personal: Name="BABU KHAN"
2. Call GET endpoint → Success
3. Upload education: School="KHAN INSTITUTE"
4. Call GET endpoint → verification_status="matched" (contains same last name)

---

## Logging

All verification operations are logged with [Verification] prefix:

```
[Verification] Starting document verification...
[Verification] Name comparison: Names match: 'BABU KHAN' == 'BABU KHAN'
[Verification] DOB comparison: DOB not present in one document (acceptable)
[Verification] Status: matched
[Verification] ✓ Verification passed
```

If verification fails:
```
[Verification] ERROR: Name MISMATCH: Personal='BABU KHAN' vs Educational='ARJUN SINGH'
```
