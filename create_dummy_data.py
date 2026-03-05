import json
import os

payload_dict = {
    "user_data": {"name": "Test User", "extracted_id": "1234 5678 9012"},
    "file_path": os.path.abspath("test_playwright.py").replace("\\", "/"),
    "portal_url": "http://127.0.0.1:8000/mock-gov-portal",
    "mock_portal_url": "file:///" + os.path.abspath("mock-gov-portal.html").replace("\\", "/")
}

with open("_temp_portal_data.json", "w", encoding="utf-8") as f:
    json.dump(payload_dict, f)

print("Created _temp_portal_data.json")
