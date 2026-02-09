# Windows File Locking Issue - RESOLVED

## Problem
When processing scanned PDFs on Windows, the system would fail with:
```
[WinError 32] The process cannot access the file because it is being used by another process: 'C:\\Users\\...\\tmp*.png'
```

This occurred because:
1. PDF converted to temporary PNG image
2. PaddleOCR processes the image and holds file lock
3. Attempt to delete temp file fails because Windows still has it locked
4. PIL Image object also holds file reference

## Root Causes
1. **PIL Image Caching** - The `images` list from `pdf2image` holds file descriptors
2. **PaddleOCR File Locking** - PaddleOCR loads image into memory but Windows doesn't fully release the file handle
3. **Timing Issue** - Garbage collection alone isn't enough; we need delays and retries

## Solution Implemented

### Changes to `services/ocr_service.py` (Lines 263-327):

**Before:**
- Used `tempfile.NamedTemporaryFile()` which causes issues on Windows
- Single retry with 0.1s delay
- No PIL object cleanup

**After:**
1. **Use stable temp directory** - Create `%TEMP%/cv_ocr_temp/` with UUID filenames instead of NamedTemporaryFile
2. **Explicit PIL cleanup** - Delete `images` list reference and call `gc.collect()`
3. **Progressive backoff retries** - 5 retry attempts with exponential backoff (0.3s, 0.6s, 0.9s, 1.2s, 1.5s)
4. **Graceful degradation** - If file can't be deleted, log warning instead of crashing (system temp cleanup will handle it)

### Key Changes:
```python
# OLD: tempfile.NamedTemporaryFile(suffix='.png', delete=False)
# NEW: temp_dir / f"pdf_page_{uuid.uuid4().hex}.png"

# OLD: No PIL cleanup
# NEW: del images; gc.collect(); time.sleep(0.05)

# OLD: 3 retries with 0.2s delay
# NEW: 5 retries with progressive backoff (0.3s * attempt)
```

## Testing

When you process a scanned PDF:
```bash
# Upload personal document (scanned PDF)
curl -X POST "http://localhost:8000/form/personal-document/upload?worker_id=YOUR_WORKER_ID" \
  -F "file=@scanned_document.pdf"

# Get worker data (triggers OCR)
curl -X GET "http://localhost:8000/form/worker/YOUR_WORKER_ID/data"
```

Expected behavior:
1. PDF text extraction returns 0 characters (scanned PDF)
2. System converts first PDF page to PNG
3. PaddleOCR processes PNG
4. Temp file deleted successfully (no WinError 32)
5. OCR text returned and saved to database

## Logs to Expect

Success:
```
WARNING - PDF has no extractable text (may be scanned PDF). Attempting OCR on first page...
INFO - Saved PDF page to temp location: C:\Users\...\cv_ocr_temp\pdf_page_abc123.png
INFO - Starting OCR on converted PDF image: ...
INFO - Successfully deleted temp file: ...
INFO - OCR on PDF first page: Extracted 2500 characters
```

If deletion fails (acceptable):
```
WARNING - Could not delete temp file after 5 attempts: ... It will be cleaned up on next system temp cleanup.
```

## Files Modified
- `/vercel/share/v0-project/services/ocr_service.py` (added uuid import, updated PDF-to-OCR conversion logic)

## Backward Compatibility
- No breaking changes
- Existing code paths unchanged
- Only affects scanned PDF handling

## Additional Notes
- The `cv_ocr_temp` folder in system temp will eventually be cleaned by OS (typically on reboot or manual temp cleanup)
- If temp cleanup is needed manually on Windows: `rmdir /S %TEMP%\cv_ocr_temp`
- Linux/Mac users unaffected (file locking not an issue on Unix systems)
