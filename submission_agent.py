import os
import re
import asyncio
import zipfile
import io
import json
import httpx
from playwright.async_api import async_playwright
from sarvamai import SarvamAI
from dotenv import load_dotenv

load_dotenv()

sarvam_client = SarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY"))

async def validate_document_with_sarvam(file_path: str, expected_doc_type: str):
    try:
        # Determine if we need to zip it (Sarvam only accepts PDF and ZIP)
        is_pdf = file_path.lower().endswith(".pdf")
        if not is_pdf:
            zip_path = file_path + ".zip"
            with zipfile.ZipFile(zip_path, 'w') as z:
                z.write(file_path, arcname=os.path.basename(file_path))
            upload_target = zip_path
        else:
            upload_target = file_path

        filename = os.path.basename(upload_target)
        
        # 1. Initialize Job
        job = sarvam_client.document_intelligence.initialise()
        job_id = job.job_id
        
        # 2. Get Upload Link
        links = sarvam_client.document_intelligence.get_upload_links(
            job_id=job_id, files=[filename]
        )
        upload_url = links.upload_urls[filename].file_url
        
        # 3. Upload File to Blob Storage
        with open(upload_target, "rb") as f:
            res = httpx.put(
                upload_url, 
                content=f.read(),
                headers={"x-ms-blob-type": "BlockBlob", "Content-Type": "application/octet-stream"}
            )
            if res.status_code not in (200, 201):
                return {"is_valid": False, "error": f"Failed to upload document: {res.status_code}"}
        
        # 4. Start Processing
        sarvam_client.document_intelligence.start(job_id=job_id)
        
        # 5. Poll for completion (Wait until Sarvam processes the document)
        max_retries = 30
        for _ in range(max_retries):
            status = sarvam_client.document_intelligence.get_status(job_id=job_id)
            if status.job_state in ("Completed", "PartiallyCompleted"):
                break
            if status.job_state == "Failed":
                return {"is_valid": False, "error": "Document OCR processing failed on Sarvam AI."}
            await asyncio.sleep(2) # Prevent blocking event loop
        else:
            return {"is_valid": False, "error": "Document processing timed out."}
            
        # 6. Get Download Links & Read Text
        dl_links = sarvam_client.document_intelligence.get_download_links(job_id=job_id)
        
        extracted_text = ""
        for fname, dl_info in dl_links.download_urls.items():
            res = httpx.get(dl_info.file_url)
            if fname.endswith(".zip") or b"PK\x03\x04" in res.content[:4]:
                with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                    for zname in z.namelist():
                        if zname.endswith(".json"):
                            try:
                                data = json.loads(z.read(zname))
                                for block in data.get("blocks", []):
                                    extracted_text += block.get("text", "").upper() + " "
                            except json.JSONDecodeError:
                                pass
            else:
                extracted_text += res.text.upper()
            
        print("======== EXTRACTED OCR TEXT ========\n", extracted_text.strip(), "\n====================================")
            
        # Cleanup zip if created
        if not is_pdf and os.path.exists(upload_target):
            os.remove(upload_target)
            
        if expected_doc_type.lower() in ("aadhaar", "aadhar"):
            # Looks for 12 digits: 1234 5678 9012 (handles arbitrary whitespace or newlines)
            match = re.search(r'\b\d{4}\s*\d{4}\s*\d{4}\b', extracted_text)
            if match:
                return {"is_valid": True, "extracted_id": match.group()}
            elif "INCOME TAX DEPARTMENT" in extracted_text:
                return {"is_valid": False, "error": "You uploaded a PAN Card. Please upload an Aadhaar Card."}
                
        elif expected_doc_type.lower() == "pan":
            # Looks for 5 letters, 4 numbers, 1 letter: ABCDE1234F
            match = re.search(r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b', extracted_text)
            if match:
                return {"is_valid": True, "extracted_id": match.group()}
            elif "GOVERNMENT OF INDIA" in extracted_text and re.search(r'\b\d{4}\s?\d{4}\s?\d{4}\b', extracted_text):
                 return {"is_valid": False, "error": "You uploaded an Aadhaar Card. Please upload a PAN Card."}

        return {"is_valid": False, "error": f"Could not verify {expected_doc_type} details. Ensure the document is clear."}
            
    except Exception as e:
        return {"is_valid": False, "error": str(e)}

async def submit_to_portal_agent(user_data: dict, file_path: str, portal_url: str = "http://localhost:8000/mock-gov-portal"):
    """
    The 'Action Agent': Opens a hidden browser, fills the form, and submits.
    """
    async with async_playwright() as p:
        # headless=True means the browser runs invisibly in the background
        browser = await p.chromium.launch(headless=True) 
        page = await browser.new_page()
        
        try:
            # 1. Navigate to the target portal
            await page.goto(portal_url) 
            
            # 2. Fill out the form fields using CSS selectors
            await page.fill("#applicant-name", user_data.get("name", "Citizen"))
            await page.fill("#document-id", user_data.get("extracted_id", ""))
            
            # 3. Upload the document
            await page.set_input_files("#file-upload-input", file_path)
            
            # 4. Click Submit
            await page.click("#submit-button")
            
            # 5. Wait for the success message to appear on the screen and scrape it
            await page.wait_for_selector("#success-message", timeout=5000)
            success_text = await page.locator("#success-message").inner_text()
            
            return {"status": "success", "message": success_text}
            
        except Exception as e:
            return {"status": "error", "message": f"Portal submission failed: {str(e)}"}
        finally:
            await browser.close()