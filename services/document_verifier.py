import logging
from typing import Dict, Optional, Tuple
from fuzzywuzzy import fuzz
from datetime import datetime

logger = logging.getLogger(__name__)


def fuzzy_match_name(name1: str, name2: str, threshold: float = 0.85) -> Tuple[float, bool]:
    """
    Calculate name similarity using fuzzy matching (Levenshtein distance)
    Returns: (similarity_score: 0.0-1.0, is_match: bool)
    """
    if not name1 or not name2:
        logger.warning(f"Empty names for comparison: '{name1}' vs '{name2}'")
        return 0.0, False
    
    # Normalize names: lowercase, remove extra spaces
    n1 = " ".join(name1.strip().lower().split())
    n2 = " ".join(name2.strip().lower().split())
    
    # Calculate similarity (fuzz.ratio returns 0-100)
    similarity_percent = fuzz.ratio(n1, n2)
    similarity_score = similarity_percent / 100.0
    is_match = similarity_score >= threshold
    
    logger.debug(f"Name comparison: '{name1}' vs '{name2}' -> {similarity_score:.2f} (threshold: {threshold})")
    return similarity_score, is_match


def exact_match_dob(dob1: str, dob2: str) -> bool:
    """
    Compare dates of birth for exact match
    Handles YYYY-MM-DD format
    Returns: True if exact match, False otherwise
    """
    if not dob1 or not dob2:
        logger.warning(f"Empty DOB for comparison: '{dob1}' vs '{dob2}'")
        return False
    
    # Normalize DOB format
    try:
        date1 = datetime.strptime(str(dob1).strip(), "%Y-%m-%d").date()
        date2 = datetime.strptime(str(dob2).strip(), "%Y-%m-%d").date()
        
        is_match = date1 == date2
        logger.debug(f"DOB comparison: {date1} vs {date2} -> {is_match}")
        return is_match
    except (ValueError, TypeError) as e:
        logger.warning(f"Could not parse DOB for comparison: {dob1}, {dob2} - {str(e)}")
        return False


def compare_documents(doc1: Dict, doc2: Dict, doc1_label: str, doc2_label: str, 
                     comparison_type: str, name_threshold: float = 0.85) -> Dict:
    """
    Compare two documents (personal vs educational or educational vs educational)
    Returns: {
        status: 'verified' or 'failed',
        name_match: {similarity: float, status: str, passed: bool},
        dob_match: {status: str, passed: bool},
        issues: [...]
    }
    """
    if not doc1 or not doc2:
        logger.error(f"Invalid document data for comparison: {comparison_type}")
        return {
            "status": "failed",
            "name_match": {"status": "No data", "passed": False},
            "dob_match": {"status": "No data", "passed": False},
            "issues": ["Missing document data for comparison"]
        }
    
    result = {
        "status": "verified",
        "name_match": {"passed": False},
        "dob_match": {"passed": False},
        "issues": []
    }
    
    # Extract names
    name1 = doc1.get("name") or ""
    name2 = doc2.get("name") or ""
    
    if name1 and name2:
        similarity, is_match = fuzzy_match_name(name1, name2, threshold=name_threshold)
        result["name_match"] = {
            "doc1_value": name1,
            "doc2_value": name2,
            "similarity": round(similarity, 3),
            "threshold": name_threshold,
            "status": "PASSED" if is_match else "FAILED",
            "passed": is_match
        }
        if not is_match:
            result["status"] = "failed"
            result["issues"].append(f"Name mismatch: '{name1}' vs '{name2}' (similarity: {similarity:.2%})")
    else:
        result["name_match"] = {
            "status": "SKIPPED",
            "reason": "Missing names in one or both documents",
            "passed": True  # Skip doesn't fail
        }
        logger.debug(f"Skipping name comparison: {doc1_label}='{name1}', {doc2_label}='{name2}'")
    
    # Extract DOBs
    dob1 = doc1.get("date_of_birth") or ""
    dob2 = doc2.get("date_of_birth") or ""
    
    if dob1 and dob2:
        is_match = exact_match_dob(dob1, dob2)
        result["dob_match"] = {
            "doc1_value": dob1,
            "doc2_value": dob2,
            "status": "PASSED" if is_match else "FAILED",
            "passed": is_match
        }
        if not is_match:
            result["status"] = "failed"
            result["issues"].append(f"DOB mismatch: {dob1} vs {dob2}")
    else:
        result["dob_match"] = {
            "status": "SKIPPED",
            "reason": "Missing DOB in one or both documents",
            "passed": True  # Skip doesn't fail
        }
        logger.debug(f"Skipping DOB comparison: {doc1_label}='{dob1}', {doc2_label}='{dob2}'")
    
    logger.info(f"Comparison result ({comparison_type}): {result['status']} - "
                f"Name: {result['name_match'].get('status', 'N/A')}, "
                f"DOB: {result['dob_match'].get('status', 'N/A')}")
    
    return result


def verify_worker_documents(personal: Optional[Dict], edu_10th: Optional[Dict], 
                           edu_12th: Optional[Dict], name_threshold: float = 0.85) -> Dict:
    """
    Perform all verification comparisons between documents
    Returns: {
        overall_status: 'verified' or 'failed' or 'incomplete',
        documents_count: int,
        comparisons: [{...}, ...],
        errors: [...]
    }
    """
    result = {
        "overall_status": "verified",
        "documents_count": 0,
        "comparisons": [],
        "errors": []
    }
    
    # Count available documents
    if personal:
        result["documents_count"] += 1
    if edu_10th:
        result["documents_count"] += 1
    if edu_12th:
        result["documents_count"] += 1
    
    if result["documents_count"] < 2:
        result["overall_status"] = "incomplete"
        result["errors"].append("Need at least 2 documents for verification")
        logger.warning(f"Insufficient documents for verification: {result['documents_count']}")
        return result
    
    # Perform comparisons
    comparisons_performed = 0
    comparisons_failed = 0
    
    # Personal vs 10th
    if personal and edu_10th:
        comp = compare_documents(personal, edu_10th, "Personal", "10th", 
                                "personal_vs_10th", name_threshold)
        result["comparisons"].append({
            "type": "personal_vs_10th",
            "status": comp["status"],
            "details": comp
        })
        comparisons_performed += 1
        if comp["status"] == "failed":
            comparisons_failed += 1
        logger.info(f"personal_vs_10th comparison: {comp['status']}")
    
    # Personal vs 12th
    if personal and edu_12th:
        comp = compare_documents(personal, edu_12th, "Personal", "12th",
                                "personal_vs_12th", name_threshold)
        result["comparisons"].append({
            "type": "personal_vs_12th",
            "status": comp["status"],
            "details": comp
        })
        comparisons_performed += 1
        if comp["status"] == "failed":
            comparisons_failed += 1
        logger.info(f"personal_vs_12th comparison: {comp['status']}")
    
    # 10th vs 12th
    if edu_10th and edu_12th:
        comp = compare_documents(edu_10th, edu_12th, "10th", "12th",
                                "10th_vs_12th", name_threshold)
        result["comparisons"].append({
            "type": "10th_vs_12th",
            "status": comp["status"],
            "details": comp
        })
        comparisons_performed += 1
        if comp["status"] == "failed":
            comparisons_failed += 1
        logger.info(f"10th_vs_12th comparison: {comp['status']}")
    
    # Determine overall status
    if comparisons_failed > 0:
        result["overall_status"] = "failed"
        logger.error(f"Verification FAILED: {comparisons_failed}/{comparisons_performed} comparisons failed")
    elif comparisons_performed == 0:
        result["overall_status"] = "incomplete"
        logger.warning("No comparisons could be performed")
    else:
        result["overall_status"] = "verified"
        logger.info(f"Verification PASSED: All {comparisons_performed} comparisons successful")
    
    return result


def extract_verification_errors(verification_result: Dict) -> Optional[Dict]:
    """Extract error details from verification result for storage"""
    if not verification_result or verification_result.get("overall_status") != "failed":
        return None
    
    errors = {
        "status": "failed",
        "comparisons": []
    }
    
    for comp in verification_result.get("comparisons", []):
        if comp.get("status") == "failed":
            errors["comparisons"].append({
                "type": comp.get("type"),
                "issues": comp.get("details", {}).get("issues", [])
            })
    
    return errors if errors["comparisons"] else None
