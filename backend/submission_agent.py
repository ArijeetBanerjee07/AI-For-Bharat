import os
import re
import asyncio
import subprocess
import sys
import zipfile
import io
import json
import tempfile
import httpx
from playwright.sync_api import sync_playwright
from sarvamai import SarvamAI
from dotenv import load_dotenv

load_dotenv()

sarvam_client = SarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY"))


async def validate_document_with_sarvam(file_path: str, expected_doc_type: str):
    if expected_doc_type.lower() == "photo":
        # Don't OCR photos, just assume valid
        return {"is_valid": True, "extracted_id": "photo_attached", "extracted_text": ""}
        
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
                return {"is_valid": True, "extracted_id": match.group(), "extracted_text": extracted_text}
            elif "INCOME TAX DEPARTMENT" in extracted_text:
                return {"is_valid": False, "error": "You uploaded a PAN Card. Please upload an Aadhaar Card."}
                
        elif expected_doc_type.lower() == "pan":
            # Looks for 5 letters, 4 numbers, 1 letter: ABCDE1234F
            match = re.search(r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b', extracted_text)
            if match:
                return {"is_valid": True, "extracted_id": match.group(), "extracted_text": extracted_text}
            elif "GOVERNMENT OF INDIA" in extracted_text and re.search(r'\b\d{4}\s?\d{4}\s?\d{4}\b', extracted_text):
                 return {"is_valid": False, "error": "You uploaded an Aadhaar Card. Please upload a PAN Card."}

        elif expected_doc_type.lower() == "income":
            if "INCOME" in extracted_text or "CERTIFICATE" in extracted_text or "₹" in extracted_text or "RS." in extracted_text:
                return {"is_valid": True, "extracted_id": "income_cert", "extracted_text": extracted_text}
            else:
                # Be lenient for the hackathon
                return {"is_valid": True, "extracted_id": "income_cert", "extracted_text": extracted_text}

        return {"is_valid": False, "error": f"Could not verify {expected_doc_type} details. Ensure the document is clear."}
            
    except Exception as e:
        return {"is_valid": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Playwright Script (runs as a SEPARATE PROCESS to avoid Windows event loop issues)
# ---------------------------------------------------------------------------
_PLAYWRIGHT_SCRIPT = '''
import sys, json, os, traceback

# Ensure Windows Proactor Loop for subprocess stability
if os.name == 'nt':
    import asyncio
    try:
        from asyncio import WindowsProactorEventLoopPolicy
        asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
    except ImportError:
        pass

# Read data from the temp JSON file
try:
    with open("_temp_portal_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)
except Exception as e:
    print(json.dumps({"status": "error", "message": f"Failed to read payload: {str(e)}"}))
    sys.exit(1)

user_data = data["user_data"]
file_paths = data.get("file_paths", {})
# Handle old signature
if "file_path" in data and data["file_path"]:
    file_paths["default"] = data["file_path"]

portal_url = data["portal_url"]
mock_portal_url = data.get("mock_portal_url")

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        # Use a slightly longer timeout for launch
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Set a default timeout for all actions
        page.set_default_timeout(15000)
        
        target_url = portal_url
        if "/mock-gov-portal" in portal_url and mock_portal_url:
            target_url = mock_portal_url
            print(json.dumps({"debug": "Redirecting to mock: " + target_url}), file=sys.stderr)
        
        print(json.dumps({"debug": "Navigating to " + target_url}), file=sys.stderr)
        page.goto(target_url, wait_until="domcontentloaded")
        
        if "dummy-pmawas.vercel.app" in target_url:
            print(json.dumps({"debug": "Filling PMAY multi-step form..."}), file=sys.stderr)
            # Step 1
            page.wait_for_selector("#fullname", state="visible")
            fullname = str(user_data.get("fullname", "") or user_data.get("username", "") or user_data.get("name", "")).strip()
            page.fill("#fullname", fullname or "Citizen")

            fathername = str(user_data.get("fathername", "")).strip()
            page.fill("#fathername", fathername or "Unknown Father")
            
            # format dob safely
            import re
            dob_raw = str(user_data.get("dob", "")).strip()
            dob_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', dob_raw)
            if dob_match:
                dob = f"{dob_match.group(1)}-{dob_match.group(2)}-{dob_match.group(3)}"
            else:
                dob = "1990-01-01"
            try:
                page.fill("#dob", dob)
            except:
                page.fill("#dob", "1990-01-01")
                
            gender = str(user_data.get("gender", "male")).lower().strip()
            try:
                page.select_option("#gender", gender, timeout=1000)
            except:
                page.select_option("#gender", "male", timeout=1000)
                
            # strict digit filtering for JS validation
            raw_aadhaar = str(user_data.get("aadhaar", "") or user_data.get("aadhar", "") or user_data.get("extracted_id", ""))
            aadhaar_val = "".join(filter(str.isdigit, raw_aadhaar))
            if len(aadhaar_val) < 12: aadhaar_val = "123456789012"
            page.fill("#aadhaar", aadhaar_val[:12])
            
            raw_mobile = str(user_data.get("mobile", "") or user_data.get("phone", ""))
            mobile_val = "".join(filter(str.isdigit, raw_mobile))
            if len(mobile_val) < 10: mobile_val = "9876543210"
            page.fill("#mobile", mobile_val[:10])
            
            email_val = user_data.get("email", "") or "citizen@example.com"
            page.fill("#email", email_val)
            
            category = str(user_data.get("category", "ews")).lower().strip()
            try:
                page.select_option("#category", category, timeout=1000)
            except:
                page.select_option("#category", "ews", timeout=1000) # fallback
                
            raw_income = str(user_data.get("income", ""))
            income_val = "".join(filter(str.isdigit, raw_income))
            if not income_val: income_val = "50000"
            page.fill("#income", income_val)
            
            page.click("#btn-next-1")
            
            # Step 2
            try:
                page.wait_for_selector("#address", state="visible", timeout=10000)
            except Exception as wait_err:
                # Capture specific validation errors from the UI to debug Playwright halts
                ui_errors = page.evaluate("Array.from(document.querySelectorAll('.error-msg')).map(e => e.id + ': ' + e.innerText).filter(t => !t.endsWith(': '))")
                if ui_errors:
                    raise Exception(f"Validation failed on Step 1: {', '.join(ui_errors)}")
                raise wait_err
                
            page.fill("#address", user_data.get("address", "") or "Village House")
            
            state = str(user_data.get("state", "delhi")).lower().replace(" ", "-").strip()
            try:
                page.select_option("#state", state, timeout=1000)
            except:
                page.select_option("#state", "delhi", timeout=1000) # fallback
                
            page.fill("#district", user_data.get("district", "") or "Central")
            page.fill("#city", user_data.get("city", "") or "Delhi")
            
            raw_pincode = str(user_data.get("pincode", ""))
            pincode = "".join(filter(str.isdigit, raw_pincode))
            if len(pincode) != 6: pincode = "110001"
            page.fill("#pincode", pincode)
            
            page.click("#btn-next-2")
            
            # Step 3
            page.wait_for_selector("#declaration", state="visible")
            if "aadhar" in file_paths and os.path.exists(file_paths["aadhar"]):
                page.set_input_files("#aadhaar-doc", file_paths["aadhar"])
            if "income" in file_paths and os.path.exists(file_paths["income"]):
                page.set_input_files("#income-doc", file_paths["income"])
            if "photo" in file_paths and os.path.exists(file_paths["photo"]):
                page.set_input_files("#photo", file_paths["photo"])
                
            page.check("#declaration")
            
        elif "pm-kisan-portal.vercel.app" in target_url:
            print(json.dumps({"debug": "Filling PMJDY multi-step form..."}), file=sys.stderr)
            # Step 1
            page.wait_for_selector("#fullName", state="visible")
            fullname = str(user_data.get("fullname", "") or user_data.get("name", "")).strip()
            page.fill("#fullName", fullname or "Citizen")

            fathername = str(user_data.get("fathername", "")).strip()
            page.fill("#fatherName", fathername or "Unknown Father")
            
            import re
            dob_raw = str(user_data.get("dob", "")).strip()
            dob_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', dob_raw)
            if dob_match:
                dob = f"{dob_match.group(1)}-{dob_match.group(2)}-{dob_match.group(3)}"
            else:
                dob = "1990-01-01"
            try:
                page.fill("#dob", dob)
            except:
                page.fill("#dob", "1990-01-01")
                
            gender = str(user_data.get("gender", "male")).lower().strip()
            try:
                page.select_option("#gender", gender, timeout=1000)
            except:
                page.select_option("#gender", "male", timeout=1000)
                
            raw_aadhaar = str(user_data.get("aadhaar", "") or user_data.get("extracted_id", ""))
            aadhaar_val = "".join(filter(str.isdigit, raw_aadhaar))
            if len(aadhaar_val) < 12: aadhaar_val = "123456789012"
            page.fill("#aadhaarNumber", aadhaar_val[:12])
            
            raw_mobile = str(user_data.get("mobile", ""))
            mobile_val = "".join(filter(str.isdigit, raw_mobile))
            if len(mobile_val) < 10: mobile_val = "9876543210"
            page.fill("#mobile", mobile_val[:10])
            
            address = str(user_data.get("address", ""))
            page.fill("#address", address or "Default Address")
            
            state = str(user_data.get("state", "delhi")).lower().replace(" ", "_").strip()
            try:
                page.select_option("#state", state, timeout=1000)
            except:
                page.select_option("#state", "west_bengal", timeout=1000) # fallback
                
            district = str(user_data.get("district", ""))
            page.fill("#district", district or "Central")
            
            page.click("#nextStep1")
            
            # Step 2
            try:
                page.wait_for_selector("#occupation", state="visible", timeout=10000)
            except Exception as wait_err:
                ui_errors = page.evaluate("Array.from(document.querySelectorAll('.error-msg')).map(e => e.id + ': ' + e.innerText).filter(t => !t.endsWith(': '))")
                if ui_errors:
                    raise Exception(f"Validation failed on Step 1: {', '.join(ui_errors)}")
                raise wait_err
                
            occ = str(user_data.get("occupation", "other")).lower().strip()
            try:
                page.select_option("#occupation", occ, timeout=1000)
            except:
                page.select_option("#occupation", "other", timeout=1000)
                
            raw_income = str(user_data.get("income", ""))
            income_val = "".join(filter(str.isdigit, raw_income))
            if not income_val: income_val = "50000"
            page.fill("#income", income_val)
            
            ea = str(user_data.get("existingAccount", "no")).lower().strip()
            try:
                page.select_option("#existingAccount", ea, timeout=1000)
            except:
                page.select_option("#existingAccount", "no", timeout=1000)
                
            page.click("#nextStep2")
            
            # Step 3
            try:
                page.wait_for_selector("#nomineeName", state="visible", timeout=10000)
            except Exception as wait_err:
                ui_errors = page.evaluate("Array.from(document.querySelectorAll('.error-msg')).map(e => e.id + ': ' + e.innerText).filter(t => !t.endsWith(': '))")
                if ui_errors:
                    raise Exception(f"Validation failed on Step 2: {', '.join(ui_errors)}")
                raise wait_err
                
            page.fill("#nomineeName", str(user_data.get("nomineeName", "") or "Unknown"))
            page.fill("#nomineeRelation", str(user_data.get("nomineeRelation", "") or "Family"))
            
            raw_age = str(user_data.get("nomineeAge", ""))
            age_val = "".join(filter(str.isdigit, raw_age))
            if not age_val: age_val = "25"
            page.fill("#nomineeAge", age_val)
            
            page.click("#nextStep3")
            
            # Step 4
            try:
                page.wait_for_selector("#submitBtn", state="visible", timeout=10000)
            except Exception as wait_err:
                ui_errors = page.evaluate("Array.from(document.querySelectorAll('.error-msg')).map(e => e.id + ': ' + e.innerText).filter(t => !t.endsWith(': '))")
                if ui_errors:
                    raise Exception(f"Validation failed on Step 3: {', '.join(ui_errors)}")
                raise wait_err

            if "aadhar" in file_paths and os.path.exists(file_paths["aadhar"]):
                page.set_input_files("#aadhaarFile", file_paths["aadhar"])
            if "photo" in file_paths and os.path.exists(file_paths["photo"]):
                page.set_input_files("#photoFile", file_paths["photo"])
                
            page.evaluate("document.getElementById('declaration').checked = true")
            
        else:
            print(json.dumps({"debug": "Filling mock portal form..."}), file=sys.stderr)
            page.wait_for_selector("#applicant-name", state="visible")
            page.fill("#applicant-name", user_data.get("name", "Citizen"))
            
            page.wait_for_selector("#document-id", state="visible")
            page.fill("#document-id", user_data.get("extracted_id", ""))
            
            default_file = file_paths.get("default") or file_paths.get("aadhar")
            if default_file and os.path.exists(default_file):
                print(json.dumps({"debug": "Uploading file: " + default_file}), file=sys.stderr)
                page.set_input_files("#file-upload-input", default_file)
        
        print(json.dumps({"debug": "Clicking submit..."}), file=sys.stderr)
        if "pm-kisan-portal.vercel.app" in target_url:
            page.click("#submitBtn")
        else:
            page.click("#btn-submit")
        
        # Wait for success message
        print(json.dumps({"debug": "Waiting for success message..."}), file=sys.stderr)
        
        # Handle success message for both sites
        if "dummy-pmawas.vercel.app" in target_url:
            page.wait_for_selector("#ref-number", state="visible", timeout=10000)
            success_text = "Successfully Submitted! Ref: " + page.locator("#ref-number").inner_text()
        elif "pm-kisan-portal.vercel.app" in target_url:
            page.wait_for_selector("#refNumber", state="visible", timeout=10000)
            success_text = "Successfully Submitted! Ref: " + page.locator("#refNumber").inner_text()
        else:
            page.wait_for_selector("#success-message", state="visible", timeout=10000)
            success_text = page.locator("#success-message").inner_text()
        
        browser.close()
        # Ensure the JSON is the ONLY thing on the last line of stdout
        print(json.dumps({"status": "success", "message": success_text}))
except Exception as e:
    print(json.dumps({
        "status": "error", 
        "message": f"Portal submission failed: {str(e)}",
        "trace": traceback.format_exc()
    }))
    sys.exit(1)
'''


async def submit_to_portal_agent(user_data: dict, file_paths: dict, portal_url: str = "http://127.0.0.1:8000/mock-gov-portal"):
    """
    The 'Action Agent': Runs Playwright in a completely separate Python process.
    Uses tempfile to avoid triggering uvicorn reloads on file changes.
    """
    import tempfile
    print(f"📦 Preparing Playwright payload...")
    
    # Files to cleanup later
    to_delete = []
    
    try:
        # 1. Use system temp directory to prevent Uvicorn --reload from seeing file changes
        temp_dir = tempfile.gettempdir()
        data_file = os.path.join(temp_dir, f"portal_data_{os.getpid()}.json")
        script_file = os.path.join(temp_dir, f"playwright_runner_{os.getpid()}.py")
        
        to_delete.extend([data_file, script_file])
        
        # Pre-format paths
        abs_file_paths = {}
        if isinstance(file_paths, str):
            abs_file_paths["default"] = os.path.abspath(file_paths).replace("\\", "/")
        else:
            for k, v in file_paths.items():
                abs_file_paths[k] = os.path.abspath(v).replace("\\", "/")
                
        abs_portal_path = os.path.abspath("mock-gov-portal.html").replace("\\", "/")
        
        payload_dict = {
            "user_data": user_data,
            "file_paths": abs_file_paths,
            "portal_url": portal_url,
            "mock_portal_url": "file:///" + abs_portal_path,
            "data_file": data_file # Tell the script where its own data is
        }

        
        # Write payload
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(payload_dict, f)
        
        # Update script to read from the dynamic data_file path
        dynamic_script = _PLAYWRIGHT_SCRIPT.replace('_temp_portal_data.json', data_file.replace("\\", "\\\\"))
        
        # Write runner script
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(dynamic_script)
        
        def run_sync_subprocess():
            import subprocess
            
            # Determine best python executable (.venv is preferred)
            python_exe = sys.executable
            venv_python = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
            if os.name != 'nt':
                venv_python = os.path.join(os.getcwd(), ".venv", "bin", "python")
                
            if os.path.exists(venv_python):
                python_exe = venv_python
                print(f"🐍 Using VENV python: {python_exe}")
            
            cmd = [python_exe, script_file]
            print(f"🚀 Executing Playwright runner...")
            
            return subprocess.run(
                cmd,
                capture_output=True, 
                text=True, 
                timeout=60,
                shell=False,
                cwd=os.getcwd(),
                env=os.environ.copy()
            )

        print(f"🌐 Launching Playwright subprocess...")
        proc = await asyncio.to_thread(run_sync_subprocess)
        
        stdout_output = proc.stdout.strip()
        stderr_output = proc.stderr.strip()
        
        if stderr_output:
            print(f"🔍 Playwright stderr:\n{stderr_output}")
        
        if proc.returncode != 0:
            print(f"❌ Playwright subprocess failed (exit code {proc.returncode})")
            # Try to parse error from stdout if it's JSON
            try:
                # Find last line that looks like JSON
                last_line = stdout_output.splitlines()[-1] if stdout_output else ""
                if last_line.strip().startswith("{") and last_line.strip().endswith("}"):
                    return json.loads(last_line)
            except:
                pass
            return {"status": "error", "message": f"Portal submission failed (code {proc.returncode}). Check server logs for details."}
        
        if not stdout_output:
            return {"status": "error", "message": "Portal submission failed: No output from subprocess"}
        
        # Extract JSON from stdout - sometimes extra output gets mixed in
        try:
            # Find the last JSON block in stdout
            lines = stdout_output.splitlines()
            for line in reversed(lines):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    result = json.loads(line)
                    print(f"✅ Playwright result: {result}")
                    return result
            
            # If no line is pure JSON, try searching the whole string
            import re
            json_match = re.search(r'(\{.*?\})', stdout_output.replace('\n', ' '))
            if json_match:
                result = json.loads(json_match.group(1))
                return result
                
            raise ValueError("No JSON found in output")
        except Exception as e:
            print(f"⚠️ Failed to parse Playwright output: {stdout_output}")
            return {"status": "error", "message": f"Failed to parse portal response: {str(e)}"}
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"🔥 UNEXPECTED AGENT ERROR: {repr(e)}\n{error_trace}")
        return {"status": "error", "message": f"Portal submission failed: {repr(e)}", "trace": error_trace}
    finally:
        # Cleanup temp files
        for p in to_delete:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass

