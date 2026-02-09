# Endpoint Flow Verification - Complete System Check

## Overview
This document verifies that all endpoints are properly calling their corresponding functions and services, and that exp_ready flag flows correctly from database to frontend.

---

## Complete Flow: Transcript Submission to CV Generation

### Step 1: Voice Webhook Receives Transcript
**Endpoint:** `POST /voice/call/webhook`  
**Location:** `api/voice.py:25`  
**Functions Called:**
- ✓ `crud.get_voice_session(call_id)` - Get or create voice session
- ✓ `crud.create_voice_session(call_id, worker_id, phone_number)` - Auto-create if needed
- ✓ `crud.link_call_to_worker(call_id, worker_id)` - Link call to worker
- ✓ `conversation_engine.determine_next_step()` - Determine conversation flow
- ✓ `conversation_engine.parse_*_response()` - Parse user responses (skill, experience, etc.)
- ✓ `crud.update_voice_session()` - Update session with accumulated responses

**Database Update:** Voice session updated with responses and current_step

---

### Step 2: Transcript Submitted for Experience Extraction
**Endpoint:** `POST /voice/transcript/submit` (integrated into webhook processing)  
**Location:** `api/voice.py:330-530`  
**Functions Called:**
- ✓ `extract_from_transcript_comprehensive(transcript)` - Extract experience from transcript
- ✓ `extract_from_transcript()` - Fallback extraction
- ✓ `crud.update_voice_session()` - **CRITICAL: Sets exp_ready=True here**
  - Parameter: `exp_ready=True` (boolean)
  - Conversion: Line 830 converts Python bool(True) → SQLite int(1)
  - Logging: Line 831 logs the conversion
- ✓ `crud.get_voice_session(call_id)` - Verify database update
- ✓ `crud.get_latest_voice_session_by_worker(worker_id)` - Get latest session

**Database Update:**
- `voice_sessions.exp_ready = 1` (integer in database)
- `voice_sessions.transcript = "full transcript text"`
- `voice_sessions.experience_json = "{"job_title": "..."}"`
- `voice_sessions.status = "completed"`
- `voice_sessions.current_step = 4`

**Logging:**
- `[DB_UPDATE] Setting exp_ready=TRUE`
- `[DB_VERIFY] Database query result: exp_ready=1`
- `[DB_VERIFY] ✓ VERIFIED: exp_ready flag is TRUE in database`

---

### Step 3: Frontend Polls Worker Data (CRITICAL - THIS WAS MISSING)
**Endpoint:** `GET /form/worker/{worker_id}/data` - **NEWLY CREATED**  
**Location:** `api/form.py:2007-2151`  
**Functions Called:**
- ✓ `crud.get_worker(worker_id)` - Get worker basic info
- ✓ `crud.get_education_by_worker(worker_id)` - Get education records
- ✓ `crud.has_experience(worker_id)` - Check if experience already saved
- ✓ `_worker_has_cv(worker_id)` - Check if CV generated
- ✓ `crud.get_ocr_status(worker_id)` - Get OCR processing status
- ✓ **`crud.get_latest_voice_session_by_worker(worker_id)`** - **THIS IS THE KEY FUNCTION**

**The Key Function Chain:**
```
GET /form/worker/{worker_id}/data
  ↓
crud.get_latest_voice_session_by_worker(worker_id)  [db/crud.py:1001]
  ↓
Fetches from: SELECT * FROM voice_sessions WHERE worker_id = ? ORDER BY updated_at DESC LIMIT 1
  ↓
Retrieves: exp_ready (raw value from database: 0 or 1)
  ↓
Converts: bool(exp_ready) at line 1024  [0 → False, 1 → True]
  ↓
Returns: session_dict with exp_ready as Python boolean (True/False)
  ↓
API endpoint receives boolean True
  ↓
Logs: [RESPONSE] exp_ready in response: True
  ↓
Returns JSON: {"exp_ready": true, ...}
```

**Database Read:**
- Reads from: `voice_sessions` table
- Field: `exp_ready = 1` (integer in database)
- Function conversion: `session_dict['exp_ready'] = bool(1)` → `True`

**JSON Response (when exp_ready=true):**
```json
{
  "status": "success",
  "worker": {...},
  "education": [...],
  "has_experience": false,
  "has_cv": false,
  "ocr_status": "pending",
  "exp_ready": true,                    // ← BOOLEAN TRUE
  "experience": {...},                  // ← Included when exp_ready=true
  "call_id": "call-abc-123",           // ← Included when exp_ready=true
  "message": "Waiting for documents"
}
```

**Logging:**
- `[VOICE SESSION] Raw exp_ready from DB: 1 (type: int)`
- `[VOICE SESSION] Converted exp_ready to boolean: True`
- `[EXP_READY] ✓ Experience data found and parsed (exp_ready=True)`
- `[RESPONSE] exp_ready in response: True`

---

### Step 4: User Reviews/Edits Experience

Frontend displays extracted experience data for user review and editing.

---

### Step 5: User Confirms Experience
**Endpoint:** `POST /voice/experience/confirm`  
**Location:** `api/voice.py:531-659`  
**Functions Called:**
- ✓ `crud.get_worker(worker_id)` - Validate worker exists
- ✓ `crud.get_voice_session(call_id)` - Get voice session
- ✓ `crud.save_experience(worker_id, experience)` - Save experience to work_experience table
- ✓ `crud.get_educational_documents(worker_id)` - Get education data
- ✓ `save_cv()` - Generate CV from experience
- ✓ `prepare_for_chromadb()` - Prepare embedding
- ✓ `vector_db.add_document()` - Store embedding

**Database Updates:**
- Saves to: `work_experience` table
- Generates: CV file in `CVS_DIR`
- Updates: Vector database embedding

**Response:**
```json
{
  "status": "success",
  "call_id": "call-abc-123",
  "worker_id": "worker-def-456",
  "experience_saved": true,
  "cv_generated": true,
  "cv_path": "/cvs/CV_worker-def-456_timestamp.html",
  "has_cv": true
}
```

---

### Step 6: Frontend Polls Again (CV Generated)
**Endpoint:** `GET /form/worker/{worker_id}/data`  
**Response (when CV is generated):**
```json
{
  "status": "success",
  "worker": {...},
  "education": [...],
  "has_experience": true,
  "has_cv": true,
  "ocr_status": "completed",
  "exp_ready": true,
  "experience": {...},
  "call_id": "call-abc-123",
  "message": "CV generated successfully"
}
```

---

## Root Cause of exp_ready Not Returning True

### Problem Identified:
**The `GET /form/worker/{worker_id}/data` endpoint was MISSING**

### Solution Implemented:
Created `GET /form/worker/{worker_id}/data` endpoint that:
1. Calls `crud.get_latest_voice_session_by_worker(worker_id)`
2. The CRUD function converts exp_ready from integer (1) to boolean (True)
3. Returns proper JSON with `"exp_ready": true`

### Database Flow:
```
Database: exp_ready = 1 (integer)
         ↓
CRUD Function (get_latest_voice_session_by_worker):
  session_dict['exp_ready'] = bool(1)  # Converts to True
         ↓
API Endpoint receives: True (boolean)
         ↓
JSON Response: {"exp_ready": true}
         ↓
Frontend receives: exp_ready === true
```

---

## Key Functions and Their Roles

### Database Update Functions
| Function | Location | Purpose |
|----------|----------|---------|
| `update_voice_session()` | `db/crud.py:797` | Sets exp_ready=True after extraction |
| `save_experience()` | `db/crud.py:755` | Saves confirmed experience to work_experience |

### Database Read Functions
| Function | Location | Purpose |
|----------|----------|---------|
| `get_latest_voice_session_by_worker()` | `db/crud.py:1001` | **KEY FUNCTION: Reads exp_ready with boolean conversion** |
| `get_latest_voice_session_by_worker()` | Converts integer (0/1) to boolean (False/True) |

### Experience Extraction Functions
| Function | Location | Purpose |
|----------|----------|---------|
| `extract_from_transcript_comprehensive()` | `services/experience_extractor.py` | Extracts structured experience from transcript |
| `extract_from_responses()` | `services/experience_extractor.py` | Structures responses into JSON |
| `structure_with_openai()` | `services/experience_extractor.py` | LLM-based structuring |

### API Endpoints
| Endpoint | Location | Status |
|----------|----------|--------|
| `POST /voice/call/webhook` | `api/voice.py:25` | ✓ EXISTS |
| `GET /form/worker/{worker_id}/data` | `api/form.py:2007` | ✓ CREATED |
| `POST /voice/experience/confirm` | `api/voice.py:531` | ✓ EXISTS |

---

## Verification Checklist

- [x] POST /voice/call/webhook calls all functions correctly
- [x] Experience extraction triggered and exp_ready set to true
- [x] `update_voice_session()` called with exp_ready=True parameter
- [x] Database exp_ready field updated to 1
- [x] `GET /form/worker/{worker_id}/data` endpoint created
- [x] Endpoint calls `get_latest_voice_session_by_worker()`
- [x] CRUD function converts exp_ready (1) → boolean (true)
- [x] Response includes `"exp_ready": true` in JSON
- [x] `POST /voice/experience/confirm` endpoint exists
- [x] CV generation after confirmation properly implemented
- [x] Logging added at each critical step

---

## Log Trace Example

When frontend calls `GET /form/worker/{worker_id}/data`, you should see in logs:

```
[GET_WORKER_DATA] Fetching worker data for worker-123
[GET_WORKER_DATA] Worker found: John Doe
[VOICE SESSION] Raw exp_ready from DB: 1 (type: int)
[VOICE SESSION] Converted exp_ready to boolean: True
[EXP_READY] ✓ Experience data found and parsed (exp_ready=True)
[RESPONSE] Building final response:
[RESPONSE]   - exp_ready in response: True
[RESPONSE]   - experience in response: True
[RESPONSE]   - call_id in response: True
```

And frontend receives:
```json
{
  "exp_ready": true,
  "experience": {...},
  "call_id": "call-abc-123"
}
```

---

## Conclusion

All endpoints are now properly calling their corresponding functions. The missing `GET /form/worker/{worker_id}/data` endpoint has been created and will now correctly return `"exp_ready": true` when the database contains `exp_ready=1`.
