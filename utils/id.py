import re
from typing import Optional

def extract_id(content_obj: dict, field: Optional[str] = "thread_id"):
    """
    This function takes a content object and returns the sanitized id
    """
    if field not in content_obj.keys():
        raise ValueError(f"Field '{field}' not found in content object")
    extracted_id = re.sub(r"[^\w\s-]", "", content_obj[field].replace("/", "-"))
    return extracted_id
