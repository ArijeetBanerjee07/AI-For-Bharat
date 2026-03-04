import os
import json
import httpx
from typing import List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from submission_agent import validate_document_with_sarvam, submit_to_portal_agent
import shutil

import chromadb
from sarvamai import SarvamAI
from sentence_transformers import SentenceTransformer, CrossEncoder

load_dotenv()

app = FastAPI(title="Yojana-Setu Phygital Backend")
sarvam_client = SarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Scheme Registry: Maps schemes to required docs & portals
# ---------------------------------------------------------
# portal_url will be updated later when dummy sites are ready
SCHEME_REGISTRY = {
    "pmay-g": {
        "name": "Pradhan Mantri Awaas Yojana - Gramin (PMAY-G)",
        "required_docs": ["aadhar"],
        "portal_url": "http://localhost:8000/mock-gov-portal",
        "description": "Housing scheme for rural areas"
    },
    "pmay-u": {
        "name": "Pradhan Mantri Awaas Yojana - Urban (PMAY-U)",
        "required_docs": ["aadhar"],
        "portal_url": "http://localhost:8000/mock-gov-portal",
        "description": "Housing scheme for urban areas"
    },
    "pmjdy": {
        "name": "Pradhan Mantri Jan Dhan Yojana (PMJDY)",
        "required_docs": ["aadhar"],
        "portal_url": "http://localhost:8000/mock-gov-portal",
        "description": "Financial inclusion - bank accounts for all"
    },
    "rhiss": {
        "name": "Rural Housing Interest Subsidy Scheme (RHISS)",
        "required_docs": ["aadhar"],
        "portal_url": "http://localhost:8000/mock-gov-portal",
        "description": "Housing scheme for rural areas"
    },
}

def get_scheme_list_for_prompt():
    lines = []
    for key, info in SCHEME_REGISTRY.items():
        docs = ", ".join(info["required_docs"])
        lines.append(f"- {info['name']} (id: {key}) — requires: {docs}")
    return "\n".join(lines)

# ---------------------------------------------------------
# RAG Setup: Load Models and Database
# ---------------------------------------------------------
print("Loading Embedding Models (this might take a few seconds)...")
# Bi-Encoder (Stage 1: Fast Search)
bi_encoder = SentenceTransformer('all-MiniLM-L6-v2')
# Cross-Encoder (Stage 3: High-Accuracy Reranking)
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

# Connect to the ChromaDB we built
chroma_client = chromadb.PersistentClient(path="./yojana_setu_db")
collection = chroma_client.get_collection(name="government_schemes")
print("Database connected!")

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------

def high_quality_search(query, fetch_k=20, top_n=3):
    # Step 1: Semantic Search (fetch_k results)
    query_embedding = bi_encoder.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=fetch_k  # Grab a larger pool first
    )
    
    if not results['documents'] or not results['documents'][0]:
        return []
        
    documents = results['documents'][0]
    metadatas = results['metadatas'][0]

    # Step 2: Reranking (Cross-Encoder)
    # We pair the query with each document to get a specific relevance score
    sentence_pairs = [[query, doc] for doc in documents]
    scores = reranker.predict(sentence_pairs)

    # Sort documents by their reranker scores
    reranked_results = sorted(
        list(zip(documents, metadatas, scores)),
        key=lambda x: x[2],
        reverse=True
    )

    # Return only the top_n highest quality chunks
    return [doc for doc, meta, score in reranked_results[:top_n]]

async def get_sarvam_stream(system_prompt: str, user_query: str):
    url = "https://api.sarvam.ai/v1/chat/completions"
    headers = {
        "api-subscription-key": os.getenv("SARVAM_API_KEY", ""),
        "Content-Type": "application/json"
    }
    payload = {
        "model": "sarvam-m",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ],
        "stream": True
    }
    
    async with httpx.AsyncClient() as client:
        # Use httpx to stream the Sarvam LLM response back
        async with client.stream("POST", url, headers=headers, json=payload, timeout=60.0) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                # Yield error to frontend in case auth or LLM fails
                yield f"data: {json.dumps({'error': f'Sarvam API Error: {response.status_code} - {error_body.decode()}'})}\n\n"
                yield "data: [DONE]\n\n"
                return
                
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        yield "data: [DONE]\n\n"
                        break
                    if not data_str:
                        continue
                    try:
                        data = json.loads(data_str)
                        if "choices" in data and len(data["choices"]) > 0:
                            content = data["choices"][0].get("delta", {}).get("content")
                            if content:
                                yield f"data: {json.dumps({'content': content})}\n\n"
                    except json.JSONDecodeError:
                        pass

# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------

class ChatRequest(BaseModel):
    user_text: str
    
@app.post("/api/chat")
async def chat_with_agent(request: ChatRequest):
    user_query = request.user_text
    
    # 1. Retrieve Facts from the Database
    retrieved_facts = high_quality_search(user_query)
    
    # Format the facts into a single string
    context_string = "\n\n---\n\n".join(retrieved_facts)
    
    if not context_string:
        # Fallback if nothing is found in the DB
        context_string = "No specific scheme guidelines were found for this query."

    # 2. Build the System Prompt for Sarvam LLM
    scheme_list = get_scheme_list_for_prompt()
    system_prompt = f"""You are a helpful, empathetic "Phygital" caseworker for Yojana-Setu, assisting rural citizens in India.
Your goal is to answer their questions about government schemes clearly and simply.

You MUST base your answer ONLY on the following official guidelines and facts provided. 
If the answer is not in the facts, say you don't have that information.
Do not use jargon.

Here are the facts you must use:
{context_string}

IMPORTANT - APPLICATION WORKFLOW:
If the user wants to APPLY for a scheme, tells you they want help applying, or says "yes" to applying:
1. Tell them which documents they need to upload.
2. At the END of your response, include this EXACT tag on its own line (replace SCHEME_ID with the actual scheme id from the list below):
   [APPLY_READY:SCHEME_ID]

Available schemes you can help apply for:
{scheme_list}

If you are unsure which scheme the user wants to apply for, ask them to clarify.
Do NOT include the [APPLY_READY:...] tag if the user is just asking questions and not ready to apply.
"""

    return StreamingResponse(
        get_sarvam_stream(system_prompt, user_query), 
        media_type="text/event-stream"
    )

@app.post("/api/submit-application")
async def process_submission(
    document: UploadFile = File(...),
    doc_type: str = Form(...),
    user_name: str = Form(...)
):
    # 1. Save uploaded file temporarily
    temp_path = f"temp_{document.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(document.file, buffer)

    # 2. OCR & Validation
    validation = await validate_document_with_sarvam(temp_path, doc_type)
    
    if not validation["is_valid"]:
        os.remove(temp_path)
        # Pass the ACTUAL error from submission_agent.py to the user
        return {"agent_response": f"Document validation failed: {validation.get('error', 'Unknown error')}"}
        
    # 3. Web Automation Submission
    user_data = {"name": user_name, "extracted_id": validation["extracted_id"]}
    submission_result = await submit_to_portal_agent(user_data, temp_path)
    
    os.remove(temp_path) # Clean up

    # 4. Feed the result back to Sarvam LLM for a natural response
    if submission_result["status"] == "success":
        system_prompt = f"""You are a helpful caseworker from Team Yojana Setu. The user's name is {user_name}.
        Their application was just submitted successfully.
        The government portal returned this exact message: '{submission_result["message"]}'.
        Relay this good news to {user_name} in a warm, encouraging way and tell them what to expect next.
        IMPORTANT: Address the user by their name '{user_name}'. Sign off as 'Team Yojana Setu'.
        Do NOT use any placeholders like [User's Name] or [Contact Info]. Do NOT include any contact information or email signatures."""
    else:
        system_prompt = f"""You are a helpful caseworker from Team Yojana Setu. The user's name is {user_name}.
        The automated submission failed with this error: '{submission_result["message"]}'.
        Apologize to {user_name} by name and tell them we will try again later.
        Sign off as 'Team Yojana Setu'. Do NOT use any placeholders or include contact information."""

    # 5. Generate final conversational response
    chat_response = sarvam_client.chat.completions(
        messages=[{"role": "user", "content": system_prompt}]
    )
    
    return {
        "status": submission_result["status"],
        "agent_response": chat_response.choices[0].message.content
    }

# ---------------------------------------------------------
# Orchestrator Agent — The "Brain" 
# ---------------------------------------------------------

def detect_intent(user_text: str):
    """
    Uses Sarvam LLM to classify user intent and extract scheme info.
    Returns: {"intent": "query"|"apply", "scheme_id": str|None}
    """
    scheme_list = get_scheme_list_for_prompt()
    
    prompt = f"""You are an intent classifier for a government scheme assistant.

Analyze the user's message and determine:
1. Their INTENT: either "query" (asking questions) or "apply" (wants to apply/submit/register)
2. The SCHEME they're referring to (if any)

Available schemes:
{scheme_list}

User message: "{user_text}"

RESPOND WITH ONLY THIS EXACT JSON FORMAT, nothing else:
{{"intent": "query_or_apply", "scheme_id": "scheme_id_or_null"}}

Examples:
- "Tell me about PM Awas Yojana" → {{"intent": "query", "scheme_id": "pmay-g"}}
- "I want to apply for housing scheme" → {{"intent": "apply", "scheme_id": "pmay-g"}}
- "Yes, please help me apply" → {{"intent": "apply", "scheme_id": null}}
- "What documents do I need?" → {{"intent": "query", "scheme_id": null}}
- "Submit my application for Jan Dhan" → {{"intent": "apply", "scheme_id": "pmjdy"}}"""

    response = sarvam_client.chat.completions(
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw = response.choices[0].message.content.strip()
    print(f"🧠 Intent Detection Raw: {raw}")
    
    # Parse JSON from response
    try:
        # Handle cases where LLM wraps JSON in markdown code blocks
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        result = json.loads(raw)
        return {
            "intent": result.get("intent", "query"),
            "scheme_id": result.get("scheme_id") if result.get("scheme_id") != "null" else None
        }
    except (json.JSONDecodeError, IndexError):
        # Default to query if parsing fails
        print(f"⚠️ Intent parse failed, defaulting to query")
        return {"intent": "query", "scheme_id": None}


@app.post("/api/agent")
async def agent_orchestrator(
    user_text: str = Form(...),
    user_name: str = Form("Citizen"),
    scheme_id: Optional[str] = Form(None),
    documents: Optional[List[UploadFile]] = File(None),
    doc_types: Optional[str] = Form(None),
):
    """
    🧠 The Orchestrator Agent.
    - Detects intent via LLM
    - Routes to the correct sub-agent
    - Returns structured response with actions
    """
    has_files = documents is not None and len(documents) > 0 and documents[0].filename != ""
    
    print(f"\n{'='*50}")
    print(f"🤖 AGENT REQUEST: text='{user_text}', files={has_files}, scheme_id={scheme_id}")
    print(f"{'='*50}")
    
    # Step 1: Detect intent
    intent_result = detect_intent(user_text)
    detected_intent = intent_result["intent"]
    detected_scheme = scheme_id or intent_result["scheme_id"]  # explicit > detected
    
    print(f"🎯 Intent: {detected_intent}, Scheme: {detected_scheme}")
    
    # --------------------------------------------------
    # ROUTE 1: User is asking questions → Knowledge Agent (RAG)
    # --------------------------------------------------
    if detected_intent == "query" and not has_files:
        retrieved_facts = high_quality_search(user_text)
        context_string = "\n\n---\n\n".join(retrieved_facts)
        
        if not context_string:
            context_string = "No specific scheme guidelines were found for this query."
        
        system_prompt = f"""You are a helpful, empathetic caseworker for Yojana-Setu, assisting rural citizens in India.
Answer their question clearly and simply based ONLY on these facts:

{context_string}

If the user seems interested in applying, let them know you can help them apply.
Do not use jargon. Be warm and encouraging."""

        async def stream_with_metadata():
            # Send intent metadata first so the client knows the route
            yield f"data: {json.dumps({'meta': {'intent': 'query', 'detected_scheme': detected_scheme}})}\n\n"
            # Then stream the actual LLM response
            async for chunk in get_sarvam_stream(system_prompt, user_text):
                yield chunk

        return StreamingResponse(
            stream_with_metadata(),
            media_type="text/event-stream"
        )
    
    # --------------------------------------------------
    # ROUTE 2: User wants to apply but NO files attached
    # --------------------------------------------------
    if detected_intent == "apply" and not has_files:
        if not detected_scheme:
            return {
                "intent": "apply",
                "action": "clarify_scheme",
                "response": "I'd love to help you apply! Which scheme would you like to apply for? You can say the scheme name and I'll guide you.",
                "available_schemes": {k: v["name"] for k, v in SCHEME_REGISTRY.items()}
            }
        
        scheme = SCHEME_REGISTRY.get(detected_scheme)
        if not scheme:
            return {
                "intent": "apply",
                "action": "clarify_scheme",
                "response": f"I couldn't find a scheme with id '{detected_scheme}'.",
                "available_schemes": {k: v["name"] for k, v in SCHEME_REGISTRY.items()}
            }
        
        doc_names = ", ".join([d.upper() + " Card" for d in scheme["required_docs"]])
        return {
            "intent": "apply",
            "action": "upload_documents",
            "scheme_id": detected_scheme,
            "scheme_name": scheme["name"],
            "required_docs": scheme["required_docs"],
            "response": f"Great! To apply for {scheme['name']}, please upload the following documents: {doc_names}. Send them as file attachments along with your next message."
        }
    
    # --------------------------------------------------
    # ROUTE 3: User has files → Action Agent (Validate + Submit)
    # --------------------------------------------------
    if has_files:
        # Resolve scheme
        if not detected_scheme:
            return {
                "intent": "apply",
                "action": "clarify_scheme",
                "response": "I see you've uploaded documents, but I'm not sure which scheme you want to apply for. Please specify the scheme name or ID.",
                "available_schemes": {k: v["name"] for k, v in SCHEME_REGISTRY.items()}
            }
        
        scheme = SCHEME_REGISTRY.get(detected_scheme)
        if not scheme:
            return {
                "intent": "apply",
                "action": "clarify_scheme",
                "response": f"Unknown scheme '{detected_scheme}'.",
                "available_schemes": {k: v["name"] for k, v in SCHEME_REGISTRY.items()}
            }
        
        # Determine doc_types: explicit > auto-assign from scheme requirements
        if doc_types:
            doc_type_list = [dt.strip().lower() for dt in doc_types.split(",")]
        else:
            # Auto-assign: match files to required docs in order
            doc_type_list = scheme["required_docs"][:len(documents)]
        
        print(f"📄 Validating {len(documents)} document(s): {doc_type_list}")
        
        # Save, validate, and submit
        validated_docs = {}
        temp_paths = []
        
        for doc_file, doc_type in zip(documents, doc_type_list):
            temp_path = f"temp_{doc_file.filename}"
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(doc_file.file, buffer)
            temp_paths.append(temp_path)
            
            print(f"🔍 Validating {doc_type}: {doc_file.filename}...")
            validation = await validate_document_with_sarvam(temp_path, doc_type)
            
            if not validation["is_valid"]:
                for p in temp_paths:
                    if os.path.exists(p):
                        os.remove(p)
                return {
                    "intent": "apply",
                    "status": "error",
                    "action": "reupload",
                    "failed_doc": doc_type,
                    "response": f"Document validation failed for {doc_type}: {validation.get('error', 'Unknown error')}. Please upload a clearer document."
                }
            
            validated_docs[doc_type] = {
                "path": temp_path,
                "extracted_id": validation["extracted_id"]
            }
        
        print(f"✅ All documents validated! Submitting to portal...")
        
        # Submit to portal
        primary_doc_type = scheme["required_docs"][0]
        primary_id = validated_docs[primary_doc_type]["extracted_id"]
        primary_path = validated_docs[primary_doc_type]["path"]
        
        user_data = {"name": user_name, "extracted_id": primary_id}
        submission_result = await submit_to_portal_agent(
            user_data, primary_path, portal_url=scheme["portal_url"]
        )
        
        # Cleanup
        for p in temp_paths:
            if os.path.exists(p):
                os.remove(p)
        
        # Generate natural response via LLM
        if submission_result["status"] == "success":
            llm_prompt = f"""You are a caseworker from Team Yojana Setu. The user is {user_name}.
            Their application for '{scheme['name']}' was submitted successfully.
            Portal message: '{submission_result["message"]}'.
            Congratulate {user_name} warmly. Sign off as 'Team Yojana Setu'.
            Do NOT use placeholders or contact info."""
        else:
            llm_prompt = f"""You are a caseworker from Team Yojana Setu. The user is {user_name}.
            Application for '{scheme['name']}' failed: '{submission_result["message"]}'.
            Apologize to {user_name}. Sign off as 'Team Yojana Setu'. No placeholders."""

        chat_response = sarvam_client.chat.completions(
            messages=[{"role": "user", "content": llm_prompt}]
        )
        
        return {
            "intent": "apply",
            "status": submission_result["status"],
            "scheme": scheme["name"],
            "response": chat_response.choices[0].message.content
        }

# ---------------------------------------------------------
# Scheme Application Workflow Endpoint (Direct, non-agentic)

@app.get("/api/schemes")
async def get_schemes():
    """Returns the list of schemes the user can apply for, with required documents."""
    result = {}
    for key, info in SCHEME_REGISTRY.items():
        result[key] = {
            "name": info["name"],
            "required_docs": info["required_docs"],
            "description": info["description"]
        }
    return result

@app.post("/api/apply")
async def apply_for_scheme(
    scheme_id: str = Form(...),
    user_name: str = Form(...),
    documents: List[UploadFile] = File(...),
    doc_types: str = Form(...)  # comma-separated list: "aadhar,pan"
):
    """
    Full application workflow:
    1. Look up the scheme in the registry
    2. Validate each uploaded document via Sarvam OCR 
    3. If all documents pass → auto-fill the scheme's portal via Playwright
    4. Return a natural language success/failure response
    """
    # 1. Validate scheme exists
    scheme = SCHEME_REGISTRY.get(scheme_id.lower())
    if not scheme:
        return {"status": "error", "agent_response": f"Unknown scheme: {scheme_id}. Please select a valid scheme."}
    
    # Parse doc_types
    doc_type_list = [dt.strip().lower() for dt in doc_types.split(",")]
    
    # Check that required docs are provided
    required = set(scheme["required_docs"])
    provided = set(doc_type_list)
    missing = required - provided
    if missing:
        return {
            "status": "error", 
            "agent_response": f"Missing required documents for {scheme['name']}: {', '.join(missing)}. Please upload all required documents."
        }
    
    # 2. Save & validate each document
    validated_docs = {}
    temp_paths = []
    
    for doc_file, doc_type in zip(documents, doc_type_list):
        temp_path = f"temp_{doc_file.filename}"
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(doc_file.file, buffer)
        temp_paths.append(temp_path)
        
        print(f"🔍 Validating {doc_type}: {doc_file.filename}...")
        validation = await validate_document_with_sarvam(temp_path, doc_type)
        
        if not validation["is_valid"]:
            # Cleanup all temp files
            for p in temp_paths:
                if os.path.exists(p):
                    os.remove(p)
            return {
                "status": "error",
                "agent_response": f"Document validation failed for {doc_type}: {validation.get('error', 'Unknown error')}"
            }
        
        validated_docs[doc_type] = {
            "path": temp_path,
            "extracted_id": validation["extracted_id"]
        }
    
    print(f"✅ All documents validated! Submitting to {scheme['name']} portal...")
    
    # 3. Auto-fill the portal (use the first document's ID as the primary identifier)
    primary_doc_type = scheme["required_docs"][0]
    primary_id = validated_docs[primary_doc_type]["extracted_id"]
    primary_path = validated_docs[primary_doc_type]["path"]
    
    user_data = {"name": user_name, "extracted_id": primary_id}
    submission_result = await submit_to_portal_agent(
        user_data, 
        primary_path, 
        portal_url=scheme["portal_url"]
    )
    
    # Cleanup temp files
    for p in temp_paths:
        if os.path.exists(p):
            os.remove(p)
    
    # 4. Generate natural language response via Sarvam LLM
    if submission_result["status"] == "success":
        system_prompt = f"""You are a helpful caseworker from Team Yojana Setu. The user's name is {user_name}.
        Their application for '{scheme['name']}' was just submitted successfully.
        The government portal returned this message: '{submission_result["message"]}'.
        Relay this good news to {user_name} in a warm, encouraging way and tell them what to expect next.
        IMPORTANT: Address the user by their name '{user_name}'. Sign off as 'Team Yojana Setu'.
        Do NOT use any placeholders like [User's Name] or [Contact Info]. Do NOT include any contact information or email signatures."""
    else:
        system_prompt = f"""You are a helpful caseworker from Team Yojana Setu. The user's name is {user_name}.
        The application for '{scheme['name']}' failed with this error: '{submission_result["message"]}'.
        Apologize to {user_name} by name and tell them we will try again later.
        Sign off as 'Team Yojana Setu'. Do NOT use any placeholders or include contact information."""

    chat_response = sarvam_client.chat.completions(
        messages=[{"role": "user", "content": system_prompt}]
    )
    
    return {
        "status": submission_result["status"],
        "scheme": scheme["name"],
        "agent_response": chat_response.choices[0].message.content
    }

# ---------------------------------------------------------
# Mock Portal & Static Routes
# ---------------------------------------------------------

@app.get("/mock-gov-portal")
async def get_mock_portal():
    with open("mock-gov-portal.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)
# To run: uvicorn main:app --reload