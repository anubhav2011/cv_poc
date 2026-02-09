import json
import logging
import sqlite3
import uuid
from typing import Optional
from app.db.database import get_db_connection

# Configure logging - ensure DEBUG level is captured
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def create_worker(worker_id: str, mobile_number: str) -> bool:
    """
    Create a new worker record.
    POC MODE: Allows same mobile_number multiple times - each signup creates a new worker_id.
    Same mobile number can be used for testing multiple times.
    """
    conn = None
    try:
        # POC: Always create new worker, even if worker_id somehow exists (shouldn't happen with UUID)
        # This allows testing with same mobile number multiple times
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO workers (worker_id, mobile_number)
        VALUES (?, ?)
        """, (worker_id, mobile_number))
        conn.commit()
        logger.info(
            f"[POC] Worker created: {worker_id} (Mobile: {mobile_number}) - Same mobile can be used multiple times for testing")

        return True
    except sqlite3.IntegrityError as e:
        # If worker_id already exists (extremely rare with UUID), generate new one
        logger.warning(f"Worker {worker_id} already exists, generating new worker_id for POC testing")
        # Generate new UUID and retry once
        new_worker_id = str(uuid.uuid4())
        try:
            cursor.execute("""
            INSERT INTO workers (worker_id, mobile_number)
            VALUES (?, ?)
            """, (new_worker_id, mobile_number))
            conn.commit()
            logger.info(f"[POC] Worker created with new ID: {new_worker_id} (Mobile: {mobile_number})")
            return True
        except Exception as retry_error:
            logger.error(f"Error creating worker with new ID: {str(retry_error)}", exc_info=True)
            return False
    except Exception as e:
        logger.error(f"Error creating worker {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def update_worker_data(worker_id: str, name: str, dob: str, address: str) -> bool:
    """Update worker personal data from OCR"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        logger.info(
            f"Updating worker data for {worker_id}: name={bool(name)}, dob={bool(dob)}, address={bool(address)}")

        cursor.execute("""
        UPDATE workers 
        SET name = ?, dob = ?, address = ?
        WHERE worker_id = ?
        """, (name, dob, address, worker_id))
        conn.commit()
        if cursor.rowcount == 0:
            logger.error(f"UPDATE workers matched 0 rows for worker_id={worker_id!r}. Worker may not exist.")
            return False
        logger.info(f"Successfully updated worker {worker_id} (rowcount={cursor.rowcount})")
        return True
    except Exception as e:
        logger.error(f"Error updating worker data {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_worker(worker_id: str) -> dict:
    """Get worker data"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workers WHERE worker_id = ?", (worker_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error getting worker {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def save_personal_document_path(worker_id: str, document_path: str) -> bool:
    """
    Save personal document path to database.
    Ensures path is absolute (resolved) for reliable retrieval across different working directories.
    """
    conn = None
    try:
        # Ensure path is absolute (resolved) for reliable retrieval
        from pathlib import Path
        resolved_path = str(Path(document_path).resolve())

        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify worker exists before updating
        cursor.execute("SELECT worker_id FROM workers WHERE worker_id = ?", (worker_id,))
        if not cursor.fetchone():
            logger.error(f"Cannot save document path: Worker {worker_id} does not exist")
            return False

        cursor.execute("""
        UPDATE workers 
        SET personal_document_path = ?
        WHERE worker_id = ?
        """, (resolved_path, worker_id))
        conn.commit()

        # Verify the update succeeded
        cursor.execute("SELECT personal_document_path FROM workers WHERE worker_id = ?", (worker_id,))
        saved_path = cursor.fetchone()
        if saved_path and saved_path[0] == resolved_path:
            logger.info(f"✓ Saved personal document path for worker {worker_id}: {resolved_path}")
            return True
        else:
            logger.error(f"Failed to verify saved path for worker {worker_id}")
            logger.error(f"  Expected: {resolved_path}")
            logger.error(f"  Found in DB: {saved_path[0] if saved_path else None}")
            return False
    except Exception as e:
        logger.error(f"Error saving personal document path for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def add_educational_document_path(worker_id: str, document_path: str) -> bool:
    """
    Add educational document path to database (stores as JSON array).
    Ensures path is absolute (resolved) for reliable retrieval across different working directories.
    """
    conn = None
    try:
        # Ensure path is absolute (resolved) for reliable retrieval
        from pathlib import Path
        resolved_path = str(Path(document_path).resolve())

        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify worker exists before updating
        cursor.execute("SELECT worker_id FROM workers WHERE worker_id = ?", (worker_id,))
        if not cursor.fetchone():
            logger.error(f"Cannot save document path: Worker {worker_id} does not exist")
            return False

        # Get existing paths
        cursor.execute("SELECT educational_document_paths FROM workers WHERE worker_id = ?", (worker_id,))
        row = cursor.fetchone()
        existing_paths = []
        if row and row[0]:
            try:
                existing_paths = json.loads(row[0])
                # Resolve all existing paths to ensure consistency
                existing_paths = [str(Path(p).resolve()) for p in existing_paths]
            except Exception as parse_error:
                logger.warning(f"Failed to parse existing educational paths for {worker_id}: {parse_error}")
                existing_paths = []

        # Add new path if not already present (compare resolved paths)
        if resolved_path not in existing_paths:
            existing_paths.append(resolved_path)

        paths_json = json.dumps(existing_paths, ensure_ascii=False)
        cursor.execute("""
        UPDATE workers 
        SET educational_document_paths = ?
        WHERE worker_id = ?
        """, (paths_json, worker_id))
        conn.commit()

        # Verify the update succeeded
        cursor.execute("SELECT educational_document_paths FROM workers WHERE worker_id = ?", (worker_id,))
        saved_row = cursor.fetchone()
        if saved_row and saved_row[0]:
            try:
                saved_paths = json.loads(saved_row[0])
                if resolved_path in saved_paths:
                    logger.info(f"✓ Added educational document path for worker {worker_id}: {resolved_path}")
                    return True
                else:
                    logger.error(f"Failed to verify saved educational path for worker {worker_id}")
                    logger.error(f"  Expected: {resolved_path}")
                    logger.error(f"  Found in DB: {saved_paths}")
                    return False
            except Exception as verify_error:
                logger.error(f"Failed to verify saved paths: {verify_error}")
                return False
        else:
            logger.error(f"No educational paths found in DB after save for worker {worker_id}")
            return False
    except Exception as e:
        logger.error(f"Error adding educational document path for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def save_video_url(worker_id: str, video_url: str) -> bool:
    """Save video resume URL (e.g. from Cloudinary) for a worker."""
    conn = None
    try:
        if not video_url or not video_url.strip().startswith("http"):
            logger.error(f"Invalid video_url for worker {worker_id}")
            return False
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT worker_id FROM workers WHERE worker_id = ?", (worker_id,))
        if not cursor.fetchone():
            logger.error(f"Cannot save video URL: Worker {worker_id} does not exist")
            return False
        cursor.execute(
            "UPDATE workers SET video_url = ? WHERE worker_id = ?",
            (video_url.strip(), worker_id)
        )
        conn.commit()
        logger.info(f"Saved video_url for worker {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving video_url for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_worker_document_paths(worker_id: str) -> dict:
    """Get document paths from database. Returns dict with 'personal' and 'educational' (list) paths."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT personal_document_path, educational_document_paths FROM workers WHERE worker_id = ?",
                       (worker_id,))
        row = cursor.fetchone()
        if row:
            personal_path = row[0] if row[0] else None
            educational_paths_json = row[1] if row[1] else None
            educational_paths = []
            if educational_paths_json:
                try:
                    educational_paths = json.loads(educational_paths_json)
                except:
                    educational_paths = []
            return {
                "personal": personal_path,
                "educational": educational_paths
            }
        return {"personal": None, "educational": []}
    except Exception as e:
        logger.error(f"Error getting document paths for {worker_id}: {str(e)}", exc_info=True)
        return {"personal": None, "educational": []}
    finally:
        if conn is not None:
            conn.close()


def get_worker_by_mobile(mobile_number: str) -> dict:
    """Get worker by mobile number"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workers WHERE mobile_number = ?", (mobile_number,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error getting worker by mobile {mobile_number}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def save_personal_document_path(worker_id: str, document_path: str) -> bool:
    """
    Save personal document path to database.
    Ensures path is absolute (resolved) for reliable retrieval across different working directories.
    """
    conn = None
    try:
        # Ensure path is absolute (resolved) for reliable retrieval
        from pathlib import Path
        resolved_path = str(Path(document_path).resolve())

        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify worker exists before updating
        cursor.execute("SELECT worker_id FROM workers WHERE worker_id = ?", (worker_id,))
        if not cursor.fetchone():
            logger.error(f"Cannot save document path: Worker {worker_id} does not exist")
            return False

        cursor.execute("""
        UPDATE workers 
        SET personal_document_path = ?
        WHERE worker_id = ?
        """, (resolved_path, worker_id))
        conn.commit()

        # Verify the update succeeded
        cursor.execute("SELECT personal_document_path FROM workers WHERE worker_id = ?", (worker_id,))
        saved_path = cursor.fetchone()
        if saved_path and saved_path[0] == resolved_path:
            logger.info(f"✓ Saved personal document path for worker {worker_id}: {resolved_path}")
            return True
        else:
            logger.error(f"Failed to verify saved path for worker {worker_id}")
            logger.error(f"  Expected: {resolved_path}")
            logger.error(f"  Found in DB: {saved_path[0] if saved_path else None}")
            return False
    except Exception as e:
        logger.error(f"Error saving personal document path for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def add_educational_document_path(worker_id: str, document_path: str) -> bool:
    """
    Add educational document path to database (stores as JSON array).
    Ensures path is absolute (resolved) for reliable retrieval across different working directories.
    """
    conn = None
    try:
        # Ensure path is absolute (resolved) for reliable retrieval
        from pathlib import Path
        resolved_path = str(Path(document_path).resolve())

        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify worker exists before updating
        cursor.execute("SELECT worker_id FROM workers WHERE worker_id = ?", (worker_id,))
        if not cursor.fetchone():
            logger.error(f"Cannot save document path: Worker {worker_id} does not exist")
            return False

        # Get existing paths
        cursor.execute("SELECT educational_document_paths FROM workers WHERE worker_id = ?", (worker_id,))
        row = cursor.fetchone()
        existing_paths = []
        if row and row[0]:
            try:
                existing_paths = json.loads(row[0])
                # Resolve all existing paths to ensure consistency
                existing_paths = [str(Path(p).resolve()) for p in existing_paths]
            except Exception as parse_error:
                logger.warning(f"Failed to parse existing educational paths for {worker_id}: {parse_error}")
                existing_paths = []

        # Add new path if not already present (compare resolved paths)
        if resolved_path not in existing_paths:
            existing_paths.append(resolved_path)

        paths_json = json.dumps(existing_paths, ensure_ascii=False)
        cursor.execute("""
        UPDATE workers 
        SET educational_document_paths = ?
        WHERE worker_id = ?
        """, (paths_json, worker_id))
        conn.commit()

        # Verify the update succeeded
        cursor.execute("SELECT educational_document_paths FROM workers WHERE worker_id = ?", (worker_id,))
        saved_row = cursor.fetchone()
        if saved_row and saved_row[0]:
            try:
                saved_paths = json.loads(saved_row[0])
                if resolved_path in saved_paths:
                    logger.info(f"✓ Added educational document path for worker {worker_id}: {resolved_path}")
                    return True
                else:
                    logger.error(f"Failed to verify saved educational path for worker {worker_id}")
                    logger.error(f"  Expected: {resolved_path}")
                    logger.error(f"  Found in DB: {saved_paths}")
                    return False
            except Exception as verify_error:
                logger.error(f"Failed to verify saved paths: {verify_error}")
                return False
        else:
            logger.error(f"No educational paths found in DB after save for worker {worker_id}")
            return False
    except Exception as e:
        logger.error(f"Error adding educational document path for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_worker_document_paths(worker_id: str) -> dict:
    """Get document paths from database. Returns dict with 'personal' and 'educational' (list) paths."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT personal_document_path, educational_document_paths FROM workers WHERE worker_id = ?",
                       (worker_id,))
        row = cursor.fetchone()
        if row:
            personal_path = row[0] if row[0] else None
            educational_paths_json = row[1] if row[1] else None
            educational_paths = []
            if educational_paths_json:
                try:
                    educational_paths = json.loads(educational_paths_json)
                except:
                    educational_paths = []
            return {
                "personal": personal_path,
                "educational": educational_paths
            }
        return {"personal": None, "educational": []}
    except Exception as e:
        logger.error(f"Error getting document paths for {worker_id}: {str(e)}", exc_info=True)
        return {"personal": None, "educational": []}
    finally:
        if conn is not None:
            conn.close()


def save_educational_document(worker_id: str, education_data: dict) -> bool:
    """Save educational document data extracted from OCR"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        logger.info(f"[EDUCATION SAVE] Saving educational document for {worker_id}")
        logger.info(f"[EDUCATION SAVE] Education data: {education_data}")

        # Convert percentage to float if it exists and is a string
        percentage = education_data.get("percentage")
        if percentage and isinstance(percentage, str):
            try:
                # Remove % symbol if present
                percentage_str = percentage.replace("%", "").strip()
                percentage = float(percentage_str) if percentage_str else None
            except (ValueError, AttributeError):
                logger.warning(f"[EDUCATION SAVE] Could not convert percentage to float: {percentage}")
                percentage = None

        cursor.execute("""
        INSERT INTO educational_documents 
        (worker_id, document_type, qualification, board, stream, year_of_passing, 
         school_name, marks_type, marks, percentage)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            worker_id,
            education_data.get("document_type"),
            education_data.get("qualification"),
            education_data.get("board"),
            education_data.get("stream"),
            education_data.get("year_of_passing"),
            education_data.get("school_name"),
            education_data.get("marks_type"),
            education_data.get("marks"),
            percentage
        ))
        conn.commit()
        logger.info(f"[EDUCATION SAVE] ✓ Educational document saved successfully for {worker_id}")
        return True
    except Exception as e:
        logger.error(f"[EDUCATION SAVE] ✗ Error saving educational document for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_educational_documents(worker_id: str) -> list:
    """Get all educational documents for a worker"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM educational_documents 
        WHERE worker_id = ? 
        ORDER BY created_at DESC
        """, (worker_id,))
        rows = cursor.fetchall()
        education_list = [dict(row) for row in rows]
        logger.info(f"[EDUCATION GET] Retrieved {len(education_list)} educational documents for worker {worker_id}")
        if education_list:
            logger.info(f"[EDUCATION GET] First record: {education_list[0]}")
        return education_list
    except Exception as e:
        logger.error(f"[EDUCATION GET] ✗ Error getting educational documents for {worker_id}: {str(e)}", exc_info=True)
        return []
    finally:
        if conn is not None:
            conn.close()


def calculate_total_experience_duration(workplaces):
    """
    Calculate total experience duration from all workplaces.
    Returns duration in months as integer.

    Expects workplaces format: [
        {
            "company_name": "ABC Corp",
            "start_date": "2020-01",
            "end_date": "2023-06",
            "duration_months": 42
        },
        ...
    ]
    """
    total_months = 0

    if not workplaces or not isinstance(workplaces, list):
        return 0

    for workplace in workplaces:
        try:
            # If duration_months is already provided, use it
            if "duration_months" in workplace and workplace["duration_months"]:
                duration = int(workplace.get("duration_months", 0))
                total_months += max(0, duration)
            # Otherwise try to calculate from dates
            elif "start_date" in workplace and "end_date" in workplace:
                from datetime import datetime
                start_str = str(workplace["start_date"]).strip()
                end_str = str(workplace["end_date"]).strip()

                # Parse dates in format YYYY-MM or YYYY-MM-DD
                if len(start_str) == 7:  # YYYY-MM format
                    start = datetime.strptime(start_str, "%Y-%m")
                else:  # YYYY-MM-DD format
                    start = datetime.strptime(start_str[:10], "%Y-%m-%d")

                if len(end_str) == 7:  # YYYY-MM format
                    end = datetime.strptime(end_str, "%Y-%m")
                else:  # YYYY-MM-DD format
                    end = datetime.strptime(end_str[:10], "%Y-%m-%d")

                months = (end.year - start.year) * 12 + (end.month - start.month)
                total_months += max(0, months)
        except (ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Could not calculate duration for workplace {workplace}: {str(e)}")
            continue

    logger.info(f"[EXPERIENCE] Calculated total duration: {total_months} months ({total_months / 12:.1f} years)")
    return total_months


def save_experience(worker_id: str, experience_data: dict) -> bool:
    """
    Save structured work experience - supports both old and new format. Updates existing if present.
    NEW: Supports multiple workplaces, current_location, availability fields.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Handle new structured format
        job_title = experience_data.get("job_title") or experience_data.get("primary_skill", "")
        total_experience = experience_data.get("total_experience", "")

        # Extract years from total_experience if needed
        experience_years = experience_data.get("experience_years", 0)
        if not experience_years and total_experience:
            import re
            years_match = re.search(r'(\d+)', str(total_experience))
            if years_match:
                experience_years = int(years_match.group(1))

        # Combine skills and tools
        skills_list = experience_data.get("skills", [])
        tools_list = experience_data.get("tools", [])
        if isinstance(skills_list, str):
            skills_list = [s.strip() for s in skills_list.split(",") if s.strip()]
        if isinstance(tools_list, str):
            tools_list = [s.strip() for s in tools_list.split(",") if s.strip()]

        # Use primary_skill if job_title not available (backward compatibility)
        primary_skill = job_title or experience_data.get("primary_skill", "")

        # Combine all skills for storage (backward compatibility)
        all_skills = list(skills_list) + list(tools_list)
        skills_json = json.dumps(all_skills, ensure_ascii=False)

        preferred_location = experience_data.get("preferred_location", "")

        # NEW: Extract comprehensive fields
        current_location = experience_data.get("current_location", "")
        availability = experience_data.get("availability", "Not specified")
        workplaces = experience_data.get("workplaces", [])
        # Ensure workplaces is a list and convert to JSON
        if not isinstance(workplaces, list):
            workplaces = []
        workplaces_json = json.dumps(workplaces, ensure_ascii=False) if workplaces else None

        logger.info(
            f"Saving experience for {worker_id}: job_title={job_title}, years={experience_years}, workplaces={len(workplaces)}")

        # Calculate total experience duration from all workplaces
        total_duration_months = calculate_total_experience_duration(workplaces)

        # Check if experience already exists - update instead of insert
        cursor.execute("SELECT id FROM work_experience WHERE worker_id = ? ORDER BY created_at DESC LIMIT 1",
                       (worker_id,))
        existing = cursor.fetchone()

        if existing:
            # Update existing experience - include new fields if available
            # NEW: Update with comprehensive fields including total_experience_duration
            cursor.execute("""
            UPDATE work_experience 
            SET primary_skill = ?, experience_years = ?, skills = ?, preferred_location = ?,
                current_location = ?, availability = ?, workplaces = ?, total_experience_duration = ?
            WHERE worker_id = ? AND id = ?
            """, (
                primary_skill,
                experience_years,
                skills_json,
                preferred_location,
                current_location if current_location else None,
                availability if availability and availability != "Not specified" else None,
                workplaces_json,
                total_duration_months,
                worker_id,
                existing["id"]
            ))
            logger.info(
                f"[EXPERIENCE] Experience updated for {worker_id}: {total_duration_months} months, {len(workplaces)} workplaces")
        else:
            # Insert new experience - include new fields
            # NEW: Insert with comprehensive fields including total_experience_duration
            cursor.execute("""
            INSERT INTO work_experience 
            (worker_id, primary_skill, experience_years, skills, preferred_location, current_location, availability, workplaces, total_experience_duration)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                worker_id,
                primary_skill,
                experience_years,
                skills_json,
                preferred_location,
                current_location if current_location else None,
                availability if availability and availability != "Not specified" else None,
                workplaces_json,
                total_duration_months
            ))
            logger.info(
                f"[EXPERIENCE] Experience saved for {worker_id}: {total_duration_months} months, {len(workplaces)} workplaces")

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving experience for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_experience(worker_id: str) -> dict:
    """
    Get work experience for worker. Also tries to get tools from voice session's experience_json if available.
    NEW: Returns workplaces array, current_location, availability if available.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM work_experience WHERE worker_id = ? ORDER BY created_at DESC LIMIT 1",
                       (worker_id,))
        row = cursor.fetchone()
        if row:
            data = dict(row)
            if data.get("skills"):
                try:
                    data["skills"] = json.loads(data["skills"])
                except (TypeError, json.JSONDecodeError):
                    data["skills"] = []

            # NEW: Parse workplaces JSON if available
            if data.get("workplaces"):
                try:
                    data["workplaces"] = json.loads(data["workplaces"])
                    if not isinstance(data["workplaces"], list):
                        data["workplaces"] = []
                except (TypeError, json.JSONDecodeError):
                    data["workplaces"] = []
            else:
                data["workplaces"] = []

            # Try to get tools from voice session's experience_json (where tools are stored separately)
            # This helps retrieve tools even if they were combined with skills in work_experience table
            if not data.get("tools"):
                cursor.execute("""
                    SELECT experience_json
                    FROM voice_sessions
                    WHERE worker_id = ? AND experience_json IS NOT NULL AND experience_json != ''
                    ORDER BY updated_at DESC
                    LIMIT 1
                """, (worker_id,))
                exp_row = cursor.fetchone()
                if exp_row and exp_row[0]:
                    try:
                        exp_data = json.loads(exp_row[0])
                        if exp_data.get("tools"):
                            data["tools"] = exp_data["tools"]
                        # NEW: Also get workplaces from experience_json if not in work_experience table
                        if not data.get("workplaces") and exp_data.get("workplaces"):
                            data["workplaces"] = exp_data["workplaces"]
                        # NEW: Get current_location and availability from experience_json if available
                        if exp_data.get("current_location") and not data.get("current_location"):
                            data["current_location"] = exp_data["current_location"]
                        if exp_data.get("availability") and not data.get("availability"):
                            data["availability"] = exp_data["availability"]
                    except (TypeError, json.JSONDecodeError):
                        pass

            # Ensure tools field exists even if empty
            if "tools" not in data:
                data["tools"] = []

            return data
        return None
    except Exception as e:
        logger.error(f"Error getting experience for {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def create_voice_session(call_id: str, worker_id: str = None, phone_number: str = None) -> bool:
    """Create a voice call session - worker_id optional (for Voice Agent generated call_id). Prevents duplicates. Sets exp_ready=0."""
    conn = None
    try:
        # Check if session already exists
        existing = get_voice_session(call_id)
        if existing:
            logger.info(f"Voice session {call_id} already exists, skipping creation")
            return True  # Return True as session exists (idempotent)

        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(
            f"Creating voice session {call_id} for worker {worker_id or 'UNKNOWN'}, phone: {phone_number or 'N/A'}")

        cursor.execute("""
        INSERT INTO voice_sessions (call_id, worker_id, phone_number, exp_ready)
        VALUES (?, ?, ?, 0)
        """, (call_id, worker_id, phone_number))
        conn.commit()
        logger.info(f"Voice session created: {call_id} (exp_ready=0)")
        return True
    except sqlite3.IntegrityError as e:
        # Handle race condition - session might have been created between check and insert
        logger.warning(f"Voice session {call_id} already exists (race condition): {str(e)}")
        return True  # Return True as session exists (idempotent)
    except Exception as e:
        logger.error(f"Error creating voice session {call_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def update_voice_session(call_id: str, step: int, status: str = "ongoing", responses_json: str = None,
                         transcript: str = None, experience_json: str = None, exp_ready: bool = None) -> bool:
    """Update voice session progress and optionally accumulated responses, transcript, experience, exp_ready flag"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(f"Updating voice session {call_id}: step={step}, status={status}")

        updates = []
        params = []

        updates.append("current_step = ?")
        params.append(step)

        updates.append("status = ?")
        params.append(status)

        if responses_json is not None:
            updates.append("responses_json = ?")
            params.append(responses_json)

        if transcript is not None:
            updates.append("transcript = ?")
            params.append(transcript)

        if experience_json is not None:
            updates.append("experience_json = ?")
            params.append(experience_json)

        if exp_ready is not None:
            # Convert boolean to integer for SQLite storage (1 for True, 0 for False)
            updates.append("exp_ready = ?")
            params.append(1 if exp_ready else 0)
            logger.info(f"Setting exp_ready={exp_ready} (stored as {1 if exp_ready else 0}) for call_id={call_id}")

        updates.append("updated_at = CURRENT_TIMESTAMP")

        query = f"""
        UPDATE voice_sessions 
        SET {', '.join(updates)}
        WHERE call_id = ?
        """
        params.append(call_id)
        
        cursor.execute(query, params)
        conn.commit()
        if cursor.rowcount == 0:
            logger.error(f"Voice session update affected 0 rows for call_id={call_id!r} - session may not exist")
            return False
        logger.info(f"Voice session updated: {call_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating voice session {call_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_voice_session(call_id: str) -> dict:
    """Get voice session details with exp_ready as boolean"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM voice_sessions WHERE call_id = ?", (call_id,))
        row = cursor.fetchone()
        if row:
            session_dict = dict(row)
            # Convert exp_ready from integer (0/1) to boolean for consistency
            if 'exp_ready' in session_dict and session_dict['exp_ready'] is not None:
                session_dict['exp_ready'] = bool(session_dict['exp_ready'])
            return session_dict
        return None
    except Exception as e:
        logger.error(f"Error getting voice session {call_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def link_call_to_worker(call_id: str, worker_id: str) -> bool:
    """Link a call_id to worker_id after transcript is collected"""
    conn = None
    try:
        # Verify worker exists
        worker = get_worker(worker_id)
        if not worker:
            logger.error(f"Worker {worker_id} not found for linking")
            return False

        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(f"Linking call_id {call_id} to worker_id {worker_id}")

        # Update voice session with worker_id
        cursor.execute("""
        UPDATE voice_sessions 
        SET worker_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE call_id = ?
        """, (worker_id, call_id))
        conn.commit()

        if cursor.rowcount == 0:
            logger.error(f"Call session {call_id} not found for linking")
            return False

        logger.info(f"Successfully linked call_id {call_id} to worker_id {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error linking call_id {call_id} to worker_id {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_cv_status(worker_id: str) -> dict:
    """Get CV status for a worker. Returns dict with has_cv flag and metadata."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cv_status WHERE worker_id = ?", (worker_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        # If no record exists, return default (no CV yet)
        logger.debug(f"No cv_status record found for worker {worker_id}, returning default (has_cv=0)")
        return None
    except Exception as e:
        logger.error(f"Error getting cv_status for {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def update_cv_status(worker_id: str, has_cv: bool = True) -> bool:
    """
    Update or create CV status for worker.
    Sets has_cv flag and cv_generated_at timestamp when CV is generated.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        logger.info(f"[CV STATUS] Updating cv_status for {worker_id}: has_cv={has_cv}")

        # Check if record exists
        cursor.execute("SELECT id FROM cv_status WHERE worker_id = ?", (worker_id,))
        existing = cursor.fetchone()

        if existing:
            # Update existing record
            if has_cv:
                cursor.execute("""
                UPDATE cv_status 
                SET has_cv = 1, cv_generated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE worker_id = ?
                """, (worker_id,))
                logger.info(f"[CV STATUS] ✓ CV status updated for {worker_id}: has_cv=1, cv_generated_at=NOW")
            else:
                cursor.execute("""
                UPDATE cv_status 
                SET has_cv = 0, cv_generated_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE worker_id = ?
                """, (worker_id,))
                logger.info(f"[CV STATUS] ✓ CV status reset for {worker_id}: has_cv=0")
        else:
            # Create new record
            if has_cv:
                cursor.execute("""
                INSERT INTO cv_status (worker_id, has_cv, cv_generated_at, created_at, updated_at)
                VALUES (?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (worker_id,))
                logger.info(f"[CV STATUS] ✓ CV status created for {worker_id}: has_cv=1, cv_generated_at=NOW")
            else:
                cursor.execute("""
                INSERT INTO cv_status (worker_id, has_cv, created_at, updated_at)
                VALUES (?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (worker_id,))
                logger.info(f"[CV STATUS] ✓ CV status created for {worker_id}: has_cv=0")

        conn.commit()

        if cursor.rowcount > 0:
            # Verify the update
            cursor.execute("SELECT has_cv FROM cv_status WHERE worker_id = ?", (worker_id,))
            result = cursor.fetchone()
            if result:
                stored_has_cv = bool(result[0])
                logger.info(f"[CV STATUS] ✓ Verified: has_cv stored in DB as {stored_has_cv}")
                return True

        logger.error(f"[CV STATUS] ✗ Failed to update cv_status for {worker_id}")
        return False
    except Exception as e:
        logger.error(f"[CV STATUS] ✗ Error updating cv_status for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_latest_voice_session_by_worker(worker_id: str) -> dict:
    """
    Get the latest voice session for a worker.
    Returns most recent session with exp_ready flag status (as boolean).
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM voice_sessions 
        WHERE worker_id = ? 
        ORDER BY updated_at DESC 
        LIMIT 1
        """, (worker_id,))
        row = cursor.fetchone()
        if row:
            session_dict = dict(row)
            # Convert exp_ready from integer (0/1) to boolean for JSON response
            exp_ready_raw = session_dict.get('exp_ready')
            logger.info(f"[VOICE SESSION] Raw exp_ready from DB: {exp_ready_raw} (type: {type(exp_ready_raw).__name__})")
            
            if 'exp_ready' in session_dict and session_dict['exp_ready'] is not None:
                session_dict['exp_ready'] = bool(session_dict['exp_ready'])
                logger.info(f"[VOICE SESSION] Converted exp_ready to boolean: {session_dict['exp_ready']}")
            else:
                logger.warning(f"[VOICE SESSION] exp_ready field missing or None")
                
            logger.info(f"[VOICE SESSION] Latest session for worker {worker_id}:")
            logger.info(f"  - call_id: {session_dict.get('call_id')}")
            logger.info(f"  - status: {session_dict.get('status')}")
            logger.info(f"  - current_step: {session_dict.get('current_step')}")
            logger.info(f"  - exp_ready: {session_dict.get('exp_ready')} (type: {type(session_dict.get('exp_ready')).__name__})")
            logger.info(f"  - has_transcript: {len(session_dict.get('transcript', '')) > 0}")
            logger.info(f"  - has_experience_json: {len(session_dict.get('experience_json', '')) > 0}")
            return session_dict
        logger.info(f"No voice sessions found for worker {worker_id}")
        return None
    except Exception as e:
        logger.error(f"Error getting latest voice session for {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def update_exp_ready(call_id: str, exp_ready: bool = True) -> bool:
    """
    Update exp_ready flag for a voice session.
    Called when experience extraction is complete and ready for user review.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        logger.info(f"[EXP READY] Updating exp_ready for call_id {call_id}: exp_ready={exp_ready}")

        # Update the flag
        cursor.execute("""
        UPDATE voice_sessions 
        SET exp_ready = ?, updated_at = CURRENT_TIMESTAMP
        WHERE call_id = ?
        """, (1 if exp_ready else 0, call_id))
        conn.commit()

        if cursor.rowcount == 0:
            logger.error(f"[EXP READY] ✗ Voice session {call_id} not found for update")
            return False

        logger.info(
            f"[EXP READY] ✓ exp_ready updated for {call_id}: exp_ready={exp_ready} (stored as {1 if exp_ready else 0})")
        return True
    except Exception as e:
        logger.error(f"[EXP READY] ✗ Error updating exp_ready for {call_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_voice_session_by_phone(phone_number: str) -> dict:
    """Get the most recent voice session by phone number with exp_ready as boolean."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM voice_sessions 
            WHERE phone_number = ? 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (phone_number,))
        row = cursor.fetchone()
        if row:
            session_dict = dict(row)
            # Convert exp_ready from integer (0/1) to boolean for consistency
            if 'exp_ready' in session_dict and session_dict['exp_ready'] is not None:
                session_dict['exp_ready'] = bool(session_dict['exp_ready'])
            return session_dict
        return None
    except Exception as e:
        logger.error(f"Error getting voice session by phone {phone_number}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()



def save_job_listing(title: str, description: str, required_skills: list, location: str) -> int:
    """Save job listing"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        skills_json = json.dumps(required_skills)
        logger.info(f"Saving job listing: {title} at {location}")

        cursor.execute("""
        INSERT INTO jobs (title, description, required_skills, location)
        VALUES (?, ?, ?, ?)
        """, (title, description, skills_json, location))
        conn.commit()
        job_id = cursor.lastrowid
        logger.info(f"Job listing saved: {job_id}")
        return job_id
    except Exception as e:
        logger.error(f"Error saving job listing: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def get_all_jobs() -> list:
    """Get all job listings"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
        rows = cursor.fetchall()
        jobs = []
        for row in rows:
            job = dict(row)
            if job.get("required_skills"):
                try:
                    job["required_skills"] = json.loads(job["required_skills"])
                except (TypeError, json.JSONDecodeError):
                    job["required_skills"] = []
            jobs.append(job)
        return jobs
    except Exception as e:
        logger.error(f"Error getting all jobs: {str(e)}", exc_info=True)
        return []
    finally:
        if conn is not None:
            conn.close()


def save_educational_document(worker_id: str, education_data: dict) -> bool:
    """Save educational document extracted data"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        logger.info(
            f"Saving educational document for {worker_id}: qualification={education_data.get('qualification')}, board={education_data.get('board')}, marks_type={education_data.get('marks_type')}")

        # Coerce percentage to float or None for REAL column
        pct = education_data.get("percentage") or None
        if pct is not None and pct != "":
            try:
                pct = float(str(pct).replace(",", ".").strip())
            except (ValueError, TypeError):
                pct = None

        cursor.execute("""
        INSERT INTO educational_documents
        (worker_id, document_type, qualification, board, stream, year_of_passing, school_name, marks_type, marks, percentage)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            worker_id,
            education_data.get("document_type", "marksheet"),
            education_data.get("qualification", ""),
            education_data.get("board", ""),
            education_data.get("stream", ""),
            education_data.get("year_of_passing", ""),
            education_data.get("school_name", ""),
            education_data.get("marks_type", ""),
            education_data.get("marks", ""),
            pct
        ))
        conn.commit()
        logger.info(f"Educational document saved successfully for {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving educational document for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_educational_documents(worker_id: str) -> list:
    """Get educational documents for worker"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM educational_documents WHERE worker_id = ? ORDER BY created_at DESC",
                       (worker_id,))
        rows = cursor.fetchall()
        docs = []
        for row in rows:
            docs.append(dict(row))
        return docs
    except Exception as e:
        logger.error(f"Error getting educational documents for {worker_id}: {str(e)}", exc_info=True)
        return []
    finally:
        if conn is not None:
            conn.close()


def create_experience_session(session_id: str, worker_id: str) -> bool:
    """Create a new experience collection session - prevents duplicates"""
    conn = None
    try:
        # Check if session already exists
        existing = get_experience_session(session_id)
        if existing:
            logger.info(f"Experience session {session_id} already exists, skipping creation")
            return True  # Return True as session exists (idempotent)

        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(f"Creating experience session {session_id} for worker {worker_id}")

        cursor.execute("""
        INSERT INTO experience_sessions (session_id, worker_id, raw_conversation, structured_data)
        VALUES (?, ?, ?, ?)
        """, (session_id, worker_id, "{}", "{}"))
        conn.commit()
        logger.info(f"Experience session created: {session_id}")
        return True
    except sqlite3.IntegrityError as e:
        # Handle race condition
        logger.warning(f"Experience session {session_id} already exists (race condition): {str(e)}")
        return True  # Return True as session exists (idempotent)
    except Exception as e:
        logger.error(f"Error creating experience session {session_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_experience_session(session_id: str) -> dict:
    """Get experience session details"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM experience_sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error getting experience session {session_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def update_experience_session(session_id: str, current_question: int, raw_conversation: dict,
                              status: str = "active") -> bool:
    """Update experience session progress"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(f"Updating experience session {session_id}: question={current_question}, status={status}")

        raw_conversation_json = json.dumps(raw_conversation, ensure_ascii=False)

        cursor.execute("""
        UPDATE experience_sessions 
        SET current_question = ?, raw_conversation = ?, status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE session_id = ?
        """, (current_question, raw_conversation_json, status, session_id))
        conn.commit()
        logger.info(f"Experience session updated: {session_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating experience session {session_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def update_experience_session_with_structured_data(session_id: str, raw_conversation: str,
                                                   structured_data: str) -> bool:
    """Update experience session with structured data after extraction"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(f"Updating experience session {session_id} with structured data")

        cursor.execute("""
        UPDATE experience_sessions 
        SET raw_conversation = ?, structured_data = ?, updated_at = CURRENT_TIMESTAMP
        WHERE session_id = ?
        """, (raw_conversation, structured_data, session_id))
        conn.commit()
        logger.info(f"Experience session updated with structured data: {session_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating experience session with structured data {session_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_experience_session_by_worker(worker_id: str) -> dict:
    """Get the latest experience session for a worker"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM experience_sessions 
        WHERE worker_id = ? 
        ORDER BY created_at DESC 
        LIMIT 1
        """, (worker_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error getting experience session for worker {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def save_pending_ocr_results(worker_id: str, personal_data: dict = None, education_data: dict = None,
                             personal_doc_path: str = None, educational_doc_path: str = None) -> bool:
    """Save pending OCR results before user review (for step-by-step workflow)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        personal_json = json.dumps(personal_data, ensure_ascii=False) if personal_data else None
        education_json = json.dumps(education_data, ensure_ascii=False) if education_data else None

        cursor.execute("""
        INSERT OR REPLACE INTO pending_ocr_results 
        (worker_id, personal_document_path, educational_document_path, personal_data_json, education_data_json, status, updated_at)
        VALUES (?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)
        """, (worker_id, personal_doc_path, educational_doc_path, personal_json, education_json))
        conn.commit()
        logger.info(f"Pending OCR results saved for worker {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving pending OCR results: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_pending_ocr_results(worker_id: str) -> dict:
    """Get pending OCR results for review"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_ocr_results WHERE worker_id = ?", (worker_id,))
        row = cursor.fetchone()

        if row:
            result = dict(row)
            # Parse JSON fields
            if result.get("personal_data_json"):
                try:
                    result["personal_data"] = json.loads(result["personal_data_json"])
                except (TypeError, json.JSONDecodeError):
                    result["personal_data"] = None
            if result.get("education_data_json"):
                try:
                    result["education_data"] = json.loads(result["education_data_json"])
                except (TypeError, json.JSONDecodeError):
                    result["education_data"] = None
            return result
        return None
    except Exception as e:
        logger.error(f"Error getting pending OCR results: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def delete_pending_ocr_results(worker_id: str) -> bool:
    """Delete pending OCR results after submission"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_ocr_results WHERE worker_id = ?", (worker_id,))
        conn.commit()
        logger.info(f"Pending OCR results deleted for worker {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting pending OCR results: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_latest_transcript_by_worker(worker_id: str) -> Optional[str]:
    """
    Get the latest transcript for a worker_id from voice sessions.
    First tries by worker_id; if none, falls back to worker's mobile_number
    and links that session to worker_id so future lookups work.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT transcript
            FROM voice_sessions
            WHERE worker_id = ? AND transcript IS NOT NULL AND transcript != ''
            ORDER BY updated_at DESC
            LIMIT 1
        """, (worker_id,))
        row = cursor.fetchone()
        if row and row[0]:
            logger.info(f"Found transcript for worker {worker_id} (length: {len(row[0])} chars)")
            return row[0]

        # Fallback: find transcript by worker's phone_number (e.g. session not yet linked)
        worker = get_worker(worker_id)
        if not worker:
            logger.info(f"No transcript found for worker {worker_id} (worker not found)")
            return None
        phone_number = worker.get("mobile_number")
        if not phone_number:
            logger.info(f"No transcript found for worker {worker_id} (no mobile)")
            return None
        cursor.execute("""
            SELECT call_id, transcript
            FROM voice_sessions
            WHERE phone_number = ? AND transcript IS NOT NULL AND transcript != ''
            ORDER BY updated_at DESC
            LIMIT 1
        """, (phone_number,))
        row = cursor.fetchone()
        if row and row[1]:
            call_id, transcript = row[0], row[1]
            cursor.execute(
                "UPDATE voice_sessions SET worker_id = ?, updated_at = CURRENT_TIMESTAMP WHERE call_id = ?",
                (worker_id, call_id)
            )
            conn.commit()
            logger.info(f"Found transcript for worker {worker_id} via phone_number, linked call_id {call_id}")
            return transcript

        logger.info(f"No transcript found for worker {worker_id}")
        return None
    except Exception as e:
        logger.error(f"Error getting transcript for worker {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def create_cv_status(worker_id: str) -> bool:
    """Create cv_status entry for a worker (called during signup)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR IGNORE INTO cv_status (worker_id, has_cv)
        VALUES (?, 0)
        """, (worker_id,))
        conn.commit()
        logger.info(f"CV status created for worker {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error creating cv_status for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_cv_status(worker_id: str) -> dict:
    """Get CV status for a worker"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cv_status WHERE worker_id = ?", (worker_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error getting cv_status for {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def mark_cv_generated(worker_id: str) -> bool:
    """Mark CV as generated for a worker"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE cv_status 
        SET has_cv = 1, cv_generated_at = CURRENT_TIMESTAMP
        WHERE worker_id = ?
        """, (worker_id,))
        conn.commit()
        if cursor.rowcount == 0:
            # If no row exists, create one
            cursor.execute("""
            INSERT INTO cv_status (worker_id, has_cv, cv_generated_at)
            VALUES (?, 1, CURRENT_TIMESTAMP)
            """, (worker_id,))
            conn.commit()
        logger.info(f"CV marked as generated for worker {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error marking CV as generated for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()
