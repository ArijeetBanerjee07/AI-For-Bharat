import os
import json
import httpx
from typing import List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from submission_agent import validate_document_with_sarvam, submit_to_portal_agent
import shutil
import uuid
import asyncio
import re

from pinecone import Pinecone
from sarvamai import SarvamAI
from groq import Groq
from sentence_transformers import SentenceTransformer, CrossEncoder
from storage_service import StorageService

load_dotenv()

# Initialize DynamoDB storage service (used by /register and /login)
storage_service = StorageService()

app = FastAPI(title="Yojana-Setu Phygital Backend")
sarvam_client = SarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY", "dummy_sarvam"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY", "dummy_groq_key"))

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
        "required_docs": ["aadhar", "income", "photo"],
        "portal_url": "https://dummy-pmawas.vercel.app/",
        "description": "Housing scheme for rural areas"
    },
    "pmay-u": {
        "name": "Pradhan Mantri Awaas Yojana - Urban (PMAY-U)",
        "required_docs": ["aadhar", "income", "photo"],
        "portal_url": "https://dummy-pmawas.vercel.app/",
        "description": "Housing scheme for urban areas"
    },
    "pmjdy": {
        "name": "Pradhan Mantri Jan Dhan Yojana (PMJDY)",
        "required_docs": ["aadhar", "photo"],
        "portal_url": "https://pm-kisan-portal.vercel.app/",
        "description": "Financial inclusion - bank accounts for all"
    },
    "rhiss": {
        "name": "Rural Housing Interest Subsidy Scheme (RHISS)",
        "required_docs": ["aadhar"],
        "portal_url": "http://127.0.0.1:8000/mock-gov-portal",
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

# Connect to Pinecone
pinecone_api_key = os.getenv("PINECONE_API_KEY")
pc = Pinecone(api_key=pinecone_api_key)
index_name = "yojana-setu"
index = pc.Index(index_name)
print("Pinecone Database connected!")

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------

def high_quality_search(query, fetch_k=20, top_n=3):
    # Step 1: Semantic Search (fetch_k results)
    query_embedding = bi_encoder.encode(query).tolist()
    
    results = index.query(
        vector=query_embedding,
        top_k=fetch_k,
        include_metadata=True
    )
    
    if not results.matches:
        return []
        
    documents = []
    metadatas = []
    
    for match in results.matches:
        meta = match.metadata or {}
        doc = meta.get('content', '')
        documents.append(doc)
        metadatas.append(meta)

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

async def async_high_quality_search(query, fetch_k=20, top_n=3):
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, high_quality_search, query, fetch_k, top_n)

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
@app.post("/register")
async def register(
    username: str = Form(...),
    fathername: str = Form(""),
    dob: str = Form(""),
    gender: str = Form(""),
    aadhaar: str = Form(""),
    phone: str = Form(...),
    email: str = Form(""),
    category: str = Form(""),
    income: str = Form(""),
    address: str = Form(""),
    state: str = Form(""),
    district: str = Form(""),
    city: str = Form(""),
    pincode: str = Form(""),
):
    """
    Registers a new user and saves to DynamoDB.
    """
    try:
        profile = {
            "user_id": phone,
            "username": username,
            "fathername": fathername,
            "dob": dob,
            "gender": gender,
            "aadhaar": aadhaar,
            "phone": phone,
            "email": email,
            "category": category,
            "income": income,
            "address": address,
            "state": state,
            "district": district,
            "city": city,
            "pincode": pincode,
            "status": "Registered"
        }
        success = storage_service.save_user_profile(profile)
        if success:
            return {"status": "Success", "message": f"User {username} registered successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to save to database")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/login")
async def login(phone: str = Form(...)):
    """
    Checks if a user exists in DynamoDB based on phone number.
    """
    try:
        profile = storage_service.get_user_profile(phone)
        if profile and (profile.get('phone') == phone or profile.get('user_id') == phone):
            return {"status": "Success", "profile": profile}
        else:
            raise HTTPException(status_code=404, detail="User not found. Please register.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_with_agent(
    user_text: str = Form(...),
    user_name: str = Form("Citizen")
):
    user_query = user_text
    
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

IMPORTANT GUIDELINES:
- When a user asks about documents needed, required information, or how to apply, give a DETAILED and STRUCTURED answer.
- List ALL specific form fields they need to fill (e.g., Full Name, Father's Name, Date of Birth, Gender, Aadhaar Number, Mobile Number, Category, Income, Address, State, District, PIN Code etc.).
- Mention exact document requirements including accepted file formats (JPG, PNG, PDF) and maximum file sizes (2MB for documents, 1MB for photos).
- For fields with dropdown options (like Gender, Category, State), list the available options.
- Use numbered sections and bullet points for clarity.

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
        system_prompt = f"""[STRICT: SUCCESS CONFIRMATION]
        The user {user_name} has successfully submitted their application.
        The portal message is: '{submission_result["message"]}'.
        REPORT THIS SUCCESS DIRECTLY. DO NOT mention technical issues, apologies, or support contacts.
        Address {user_name} by name. Sign off: Team Yojana Setu."""
    else:
        system_prompt = f"""[STRICT: FAILURE NOTIFICATION]
        The application for {user_name} failed.
        Error: '{submission_result["message"]}'.
        Briefly inform the user and apologize for the failure.
        Sign off: Team Yojana Setu."""

    # 5. Generate final conversational response
    chat_response = sarvam_client.chat.completions(model='sarvam-30b', 
        messages=[{"role": "user", "content": system_prompt}]
    )
    agent_response_text = chat_response.choices[0].message.content
    
    # This endpoint doesn't have session_id, so this part is not directly applicable here.
    # The user's instruction seems to be for the agent_orchestrator function.
    # I will apply the change to agent_orchestrator as intended.
    
    return {
        "status": submission_result["status"],
        "agent_response": agent_response_text
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

    response = sarvam_client.chat.completions(model='sarvam-30b', 
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

async def async_detect_intent(user_text: str):
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, detect_intent, user_text)

def extract_user_details(ocr_text: str):
    prompt = f"""You are a data extraction assistant. Extract personal details from the following OCR text of uploaded documents to fill a government scheme application form.

Available fields to extract (return ONLY a valid JSON object matching these keys):
- fullname (string)
- fathername (string)
- dob (string, format YYYY-MM-DD)
- gender (string, 'male', 'female', or 'other')
- aadhaar (string, 12 digits)
- mobile (string)
- email (string)
- category (string, 'ews', 'lig', 'mig1', 'mig2')
- income (int)
- address (string)
- state (string)
- district (string)
- city (string)
- pincode (string)
- occupation (string, 'farmer', 'laborer', 'self_employed', 'unemployed', 'student', 'other')
- existingAccount (string, 'yes' or 'no')
- nomineeName (string)
- nomineeRelation (string)
- nomineeAge (int)

If a field is not found in the text, omit it or leave it empty.

Text:
'''
{ocr_text}
'''
"""
    try:
        response = sarvam_client.chat.completions(model='sarvam-30b', 
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        # Ensure it's valid JSON
        return json.loads(raw)
    except Exception as e:
        print("Failed to extract details:", e)
        return {}

async def async_extract_user_details(ocr_text: str):
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, extract_user_details, ocr_text)


@app.get("/api/voice-agent/welcome")
async def get_welcome_audio():
    """
    Returns the initial welcome greeting from Shubh (male voice) as base64 audio.
    """
    try:
        greeting_text = "Namaste! Main Shubh hoon, Yojana Setu se aapka digital sahayak. Sarkari yojanaon se judi koi bhi jaankari chahiye, toh bas mujhe bataiye. Main yahan aapki sunne aur madad karne ke liye hoon. Boliye, aaj main aapki kya sahayata kar sakta hoon?"
        tts_response = sarvam_client.text_to_speech.convert(
            text=greeting_text,
            target_language_code="hi-IN",
            model="bulbul:v3",
            speaker="shubh"
        )
        audio_base64 = tts_response.audios[0] if hasattr(tts_response, 'audios') else tts_response.get("audios", [""])[0]
        return {"audio_base64": audio_base64}
    except Exception as e:
        print(f"❌ Welcome Audio Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch welcome audio")

@app.post("/api/voice-agent")
async def voice_agent_orchestrator(
    audio: UploadFile = File(...),
    user_name: str = Form("Citizen"),
    scheme_id: Optional[str] = Form(None)
):
    """
    🎤 Voice-to-Voice Agent Endpoint
    1. Transcribe audio -> Text
    2. Process Text through Orchestrator Logic
    3. Response Text -> Audio
    4. Return Text + Audio
    """
    # 1. Save temp audio
    ext = audio.filename.split(".")[-1] if audio.filename else "wav"
    temp_audio_path = f"temp_voice_{uuid.uuid4()}.{ext}"
    try:
        with open(temp_audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)
            
        # 2. Transcribe (STT) - using saarika:v2.5 which supports direct webm processing
        with open(temp_audio_path, "rb") as f:
            stt_response = sarvam_client.speech_to_text.transcribe(
                file=f,
                model="saarika:v2.5"
            )
        user_text = getattr(stt_response, "transcript", None) or getattr(stt_response, "transcription", "")
        print(f"🎙️ Voice Transcript: {user_text}")

        if not user_text or user_text.strip() == "":
            agent_text = "Maaf kijiyega, main aapki aawaz samajh nahi paya. Kripya thoda zor se aur saaf boliyee."
            detected_intent = "unknown"
            detected_scheme = None
        else:
            # 3. Decision Logic (Dynamic Language Response)
            intent_result = await async_detect_intent(user_text)
            detected_intent = intent_result["intent"]
            detected_scheme = scheme_id or intent_result["scheme_id"]
            
            # Get context if it's a query
            retrieved_facts = []
            if detected_intent == "query":
                retrieved_facts = await async_high_quality_search(user_text)
            
            context_string = "\n".join(retrieved_facts)
            
            # Unified Prompt to ensure language consistency
            voice_system_prompt = f"""You are 'Shubh', a friendly and knowledgeable AI caseworker for Yojana-Setu interacting over a voice call. 
            USER CONTEXT: Name: {user_name}, Intent: {detected_intent}, Detected Scheme: {detected_scheme}.
            FACTS FOR REFERENCE: {context_string or 'General government scheme guidance.'}
            
            TASK:
            1. If the user asks for an OVERVIEW or DETAILS of a scheme, you MUST provide a comprehensive explanation including:
               - The purpose of the scheme.
               - Who is eligible to apply.
               - Key documents needed.
               - Benefits of the scheme.
               Explain this conversationally as if talking to a citizen. Do not just give a one-line answer.
            2. If the user wants to apply and the scheme is not clear, ask them politely which scheme they are interested in.
            3. If they want to apply and the scheme IS clear, tell them which documents they need to upload to the chat.
            
            CRITICAL RULES:
            - Respond ONLY in the EXACT SAME LANGUAGE used by the user in their message: "{user_text}". 
            - Example: If the user speaks Bengali, you MUST respond in Bengali. If Hindi, in Hindi. If English, in English.
            - Keep the tone very polite, helpful, and natural (like a human talking on the phone).
            - Do not use markdown (no **bold**, no *italics*, no bullet points like -, *, 1. 2. 3.) because this text will be directly spoken by a Text-to-Speech voice engine. Use natural pauses and commas."""

            chat_response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": voice_system_prompt},
                    {"role": "user", "content": user_text}
                ],
                temperature=0.7,
                max_tokens=600
            )
            agent_text = chat_response.choices[0].message.content

        # 4. Text-to-Speech (Dynamic Language Detection)
        # Use regex to detect if there are Hindi (Devanagari) characters
        import re
        is_hindi = bool(re.search(r'[\u0900-\u097F]', agent_text))
        target_lang = "hi-IN" if is_hindi else "en-IN"
        
        print(f"🔊 AI Response ({target_lang}): {agent_text}")

        tts_response = sarvam_client.text_to_speech.convert(
            text=agent_text,
            target_language_code=target_lang,
            model="bulbul:v3",
            speaker="shubh" 
        )
        audio_base64 = tts_response.audios[0] if hasattr(tts_response, 'audios') else tts_response.get("audios", [""])[0]

        return {
            "user_text": user_text,
            "agent_text": agent_text,
            "audio_base64": audio_base64,
            "meta": {"intent": detected_intent, "scheme": detected_scheme}
        }

    except Exception as e:
        print(f"❌ Voice Agent Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

# ---------------------------------------------------------
# IVR (Twilio Phone Call) Endpoints
# ---------------------------------------------------------
from fastapi.responses import Response

@app.post("/api/ivr/welcome")
async def ivr_welcome():
    """Twilio webhook: Answers the call and greets the user, then listens."""
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Aditi" language="hi-IN">
        नमस्ते! योजना सेतु में आपका स्वागत है। मैं आपकी सरकारी योजनाओं में मदद कर सकता हूँ। कृपया अपना सवाल बोलिए।
    </Say>
    <Gather input="speech" action="/api/ivr/handle-speech" method="POST" speechTimeout="3" language="hi-IN">
        <Say voice="Polly.Aditi" language="hi-IN">मैं सुन रहा हूँ...</Say>
    </Gather>
    <Say voice="Polly.Aditi" language="hi-IN">कोई आवाज़ नहीं मिली। कृपया दोबारा कॉल करें।</Say>
</Response>"""
    return Response(content=twiml, media_type="application/xml")

@app.post("/api/ivr/handle-speech")
async def ivr_handle_speech(request: Request):
    """Twilio webhook: Receives transcribed speech, queries RAG, and speaks the answer."""
    form_data = await request.form()
    speech_result = form_data.get("SpeechResult", "")
    caller_number = form_data.get("From", "Unknown")
    
    print(f"\n📞 IVR CALL from {caller_number}")
    print(f"🎙️ Caller said: {speech_result}")
    
    if not speech_result:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Aditi" language="hi-IN">माफ कीजिये, मुझे आपकी आवाज़ नहीं सुनाई दी।</Say>
    <Redirect method="POST">/api/ivr/welcome</Redirect>
</Response>"""
        return Response(content=twiml, media_type="application/xml")
    
    try:
        # 1. Search knowledge base
        retrieved_facts = await async_high_quality_search(speech_result)
        context_string = "\n".join(retrieved_facts)
        
        # 2. Language detection
        is_hindi = bool(re.search(r'[\u0900-\u097F]', speech_result))
        target_lang = "Hindi" if is_hindi else "English"
        
        # 3. Generate response via LLM
        ivr_prompt = f"""You are 'Shubh', a friendly AI caseworker on a phone call for Yojana-Setu.
        The caller asked: "{speech_result}"
        
        FACTS: {context_string or 'General government scheme guidance.'}
        
        RULES:
        - Respond in {target_lang} ONLY.
        - Keep the answer SHORT (2-3 sentences max) since this is a phone call.
        - Be warm and helpful. End by asking if they have more questions."""

        chat_response = sarvam_client.chat.completions(model='sarvam-30b', 
            messages=[
                {"role": "system", "content": ivr_prompt},
                {"role": "user", "content": speech_result}
            ]
        )
        agent_text = chat_response.choices[0].message.content
        print(f"🤖 AI Response: {agent_text}")
        
        # 4. Use Polly voice via TwiML (simpler than Sarvam TTS for phone)
        polly_lang = "hi-IN" if is_hindi else "en-IN"
        polly_voice = "Polly.Aditi" if is_hindi else "Polly.Aditi"
        
        # Escape XML special characters
        safe_text = agent_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{polly_voice}" language="{polly_lang}">{safe_text}</Say>
    <Gather input="speech" action="/api/ivr/handle-speech" method="POST" speechTimeout="3" language="hi-IN">
        <Say voice="{polly_voice}" language="{polly_lang}">{"और कोई सवाल है तो बोलिए।" if is_hindi else "Please ask your next question."}</Say>
    </Gather>
    <Say voice="{polly_voice}" language="{polly_lang}">{"धन्यवाद! योजना सेतु की ओर से शुभकामनाएं।" if is_hindi else "Thank you for calling Yojana Setu. Goodbye!"}</Say>
</Response>"""
        return Response(content=twiml, media_type="application/xml")
        
    except Exception as e:
        print(f"❌ IVR Error: {e}")
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Aditi" language="hi-IN">माफ कीजिये, कुछ तकनीकी समस्या है। कृपया बाद में कॉल करें।</Say>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

@app.post("/api/agent")
async def agent_orchestrator(
    user_text: str = Form(...),
    user_id: str = Form("guest"),
    user_name: str = Form("Guest"),
    documents: List[UploadFile] = File(None),
    doc_types: str = Form(None),
    scheme_id: str = Form(None),
    session_id: str = Form(None)
):
    # Fetch stored user profile from database
    stored_profile = storage_service.get_user_profile(user_id) or {}
    print(f"👤 Stored profile for {user_id}: {list(stored_profile.keys())}")
    
    # Save user message
    if session_id:
        title = user_text[:50] + "..." if len(user_text) > 50 else user_text
        storage_service.save_chat_message(session_id, user_id, title, "user", user_text)
    
    # Text-based logic remains similar...
    is_hindi = any(char in user_text for char in "अआइईउऊएऐओऔ")
    
    print(f"\n{'='*50}")
    print(f"🤖 AGENT REQUEST: text='{user_text}', files={len(documents) if documents else 0}, scheme_id={scheme_id}")
    print(f"{'='*50}")
    
    # Step 1: Detect intent
    intent_result = await async_detect_intent(user_text)
    detected_intent = intent_result["intent"]
    detected_scheme = scheme_id or intent_result["scheme_id"]  # explicit > detected
    
    print(f"🎯 Intent: {detected_intent}, Scheme: {detected_scheme}")
    
    # --------------------------------------------------
    # ROUTE 1: User is asking questions → Knowledge Agent (RAG)
    # --------------------------------------------------
    if detected_intent == "query" and not documents:
        retrieved_facts = await async_high_quality_search(user_text)
        context_string = "\n\n---\n\n".join(retrieved_facts)
        
        if not context_string:
            context_string = "No specific scheme guidelines were found for this query."
        
        system_prompt = f"""You are a helpful, empathetic caseworker for Yojana-Setu, assisting rural citizens in India.
Answer their question clearly and simply based ONLY on these facts:

{context_string}

IMPORTANT GUIDELINES:
- When a user asks about documents needed, required information, or how to apply, give a DETAILED and STRUCTURED answer.
- List ALL specific form fields they need to fill (e.g., Full Name, Father's Name, Date of Birth, Gender, Aadhaar Number, Mobile Number, Category, Income, Address, State, District, PIN Code etc.).
- Mention exact document requirements including accepted file formats (JPG, PNG, PDF) and maximum file sizes (2MB for documents, 1MB for photos).
- For fields with dropdown options (like Gender, Category, State), list the available options.
- Use numbered sections and bullet points for clarity.
- If the user seems interested in applying, let them know you can help them apply by uploading their documents.
Do not use jargon. Be warm and encouraging."""

        async def stream_with_metadata():
            # Send intent metadata first so the client knows the route
            yield f"data: {json.dumps({'meta': {'intent': 'query', 'detected_scheme': detected_scheme}})}\n\n"
            
            full_response_content = ""
            async for chunk in get_sarvam_stream(system_prompt, user_text):
                # Extract content from chunk for saving
                if chunk.startswith("data:"):
                    try:
                        data = json.loads(chunk[5:].strip())
                        if "content" in data:
                            full_response_content += data["content"]
                    except json.JSONDecodeError:
                        pass
                yield chunk
            
            if session_id and full_response_content:
                storage_service.save_chat_message(session_id, user_id, "chat", "assistant", full_response_content)


        return StreamingResponse(
            stream_with_metadata(),
            media_type="text/event-stream"
        )
    
    # --------------------------------------------------
    # ROUTE 2: User wants to apply but NO files attached
    # --------------------------------------------------
    if detected_intent == "apply" and not documents:
        if not detected_scheme:
            agent_response_text = "I'd love to help you apply! Which scheme would you like to apply for? You can say the scheme name and I'll guide you."
            if session_id:
                storage_service.save_chat_message(session_id, user_id, "chat", "assistant", agent_response_text)
            return {
                "intent": "apply",
                "action": "clarify_scheme",
                "response": agent_response_text,
                "available_schemes": {k: v["name"] for k, v in SCHEME_REGISTRY.items()}
            }
        
        scheme = SCHEME_REGISTRY.get(detected_scheme)
        if not scheme:
            agent_response_text = "I didn't recognize that scheme. Which one do you want to apply for?"
            if session_id:
                storage_service.save_chat_message(session_id, user_id, "chat", "assistant", agent_response_text)
            return {
                "intent": "apply",
                "action": "clarify_scheme",
                "response": agent_response_text,
                "available_schemes": {k: v["name"] for k, v in SCHEME_REGISTRY.items()}
            }

        scheme_name = scheme["name"]
        doc_names = ", ".join([d.upper() + " Card" for d in scheme["required_docs"]])
        
        if is_hindi:
            response = f"Zaroor! {scheme_name} ke liye aapko {doc_names} upload karne honge. Kripya apne documents bhej dijiye."
        else:
            response = f"Great! To apply for {scheme_name}, please upload the following documents: {doc_names}."
        
        if session_id:
            storage_service.save_chat_message(session_id, user_id, "chat", "assistant", response)
            
        return {
            "intent": "apply",
            "action": "upload_documents",
            "scheme_id": detected_scheme,
            "scheme_name": scheme_name,
            "required_docs": scheme["required_docs"],
            "response": response
        }
    
    # --------------------------------------------------
    # ROUTE 3: User has files → Action Agent (Validate + Submit)
    # --------------------------------------------------
    if documents:
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
            if is_hindi:
                resp = f"Maaf kijiye, mujhe '{detected_scheme}' nam ki koi scheme nahi mili. Kya aap dobara bata sakte hain?"
            else:
                resp = f"Unknown scheme '{detected_scheme}'. Please specify another."
            return {
                "intent": "apply",
                "action": "clarify_scheme",
                "response": resp,
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
                if is_hindi:
                    resp = f"{doc_type} check karne mein dikkat hui: {validation.get('error', 'Unknown error')}. Kripya saaf photo upload karein."
                else:
                    resp = f"Document validation failed for {doc_type}: {validation.get('error', 'Unknown error')}. Please upload a clearer document."
                return {
                    "intent": "apply",
                    "status": "error",
                    "action": "reupload",
                    "failed_doc": doc_type,
                    "response": resp
                }
            
            validated_docs[doc_type] = {
                "path": temp_path,
                "extracted_id": validation["extracted_id"],
                "extracted_text": validation.get("extracted_text", "")
            }
        
        print(f"✅ All documents validated! Submitting to portal...")
        
        # Combine all OCR text for LLM extraction
        all_ocr_text = ""
        file_paths_dict = {}
        for dt, info in validated_docs.items():
            file_paths_dict[dt] = info["path"]
            if "extracted_text" in info:
                all_ocr_text += info["extracted_text"] + "\n\n"
        
        # Start with stored profile data, then layer on OCR extraction
        user_data = stored_profile.copy()
        user_data.update({"name": user_name, "phone": user_id}) 
        
        if all_ocr_text.strip():
            extracted_details = await async_extract_user_details(all_ocr_text)
            user_data.update(extracted_details)
        
        # Fallback for ID if still elusive
        primary_doc_type = scheme["required_docs"][0]
        primary_id = validated_docs[primary_doc_type]["extracted_id"]
        if not user_data.get("aadhaar") and not user_data.get("extracted_id"):
            user_data["extracted_id"] = primary_id
            
        submission_result = await submit_to_portal_agent(
            user_data, file_paths_dict, portal_url=scheme["portal_url"]
        )
        
        # Add the combined user data to the result so the frontend can preview it
        submission_result["user_data"] = user_data
        
        # Cleanup
        for p in temp_paths:
            if os.path.exists(p):
                os.remove(p)
        
        # Generate natural response via LLM
        target_lang = "Hindi" if is_hindi else "English"
        
        if submission_result["status"] == "success":
            llm_prompt = f"""[STRICT: SUCCESS]
            The user {user_name} has successfully applied for {scheme['name']}.
            Success Message: '{submission_result["message"]}'.
            Report success enthusiastically. 
            LANGUAGE REQUIREMENT: Respond ONLY in {target_lang}.
            Sign off: Team Yojana Setu."""
        else:
            # Provide more context to the LLM about the failure
            error_msg = submission_result.get("message", "Unknown technical error")
            llm_prompt = f"""[STRICT: FAILURE CASE]
            The application for {scheme['name']} failed.
            Technical Error: '{error_msg}'.
            Explain to {user_name} that we encountered a problem with the government portal submission.
            If it's a timeout, suggest they try again later.
            Be polite but clear about the failure.
            LANGUAGE REQUIREMENT: Respond ONLY in {target_lang}.
            Sign off: Team Yojana Setu."""

        try:
            chat_response = sarvam_client.chat.completions(model='sarvam-30b', 
                messages=[{"role": "user", "content": llm_prompt}]
            )
            response_text = chat_response.choices[0].message.content
        except Exception as e:
            print(f"⚠️ LLM response generation failed: {e}")
            if is_hindi:
                response_text = f"Maaf kijiye, application submission mein problem aayi hai: {error_msg}. Kripya dobara koshish karein."
            else:
                response_text = f"We encountered a problem with your submission: {error_msg}. Please try again later."
        
        return {
            "intent": "apply",
            "status": submission_result["status"],
            "scheme": scheme["name"],
            "response": response_text,
            "error_detail": submission_result.get("message") if submission_result["status"] != "success" else None
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
            "extracted_id": validation["extracted_id"],
            "extracted_text": validation.get("extracted_text", "")
        }
    
    print(f"✅ All documents validated! Submitting to {scheme['name']} portal...")
    
    # Combine all OCR text for LLM extraction
    all_ocr_text = ""
    file_paths_dict = {}
    for dt, info in validated_docs.items():
        file_paths_dict[dt] = info["path"]
        if "extracted_text" in info:
            all_ocr_text += info["extracted_text"] + "\n\n"
            
    # Extract user details using LLM
    user_data = {"name": user_name} # Base
    if all_ocr_text.strip():
        extracted_details = await async_extract_user_details(all_ocr_text)
        user_data.update(extracted_details)

    # Fallback to the main ID if missing
    primary_doc_type = scheme["required_docs"][0]
    primary_id = validated_docs[primary_doc_type]["extracted_id"]
    if "extracted_id" not in user_data:
        user_data["extracted_id"] = primary_id
        
    submission_result = await submit_to_portal_agent(
        user_data, 
        file_paths_dict, 
        portal_url=scheme["portal_url"]
    )
    
    # Cleanup temp files
    for p in temp_paths:
        if os.path.exists(p):
            os.remove(p)
    
    # 4. Generate natural language response via Sarvam LLM
    if submission_result["status"] == "success":
        system_prompt = f"""[STRICT: SUCCESS]
        The user {user_name} successfully applied for {scheme['name']}.
        Portal message: '{submission_result["message"]}'.
        REPORT SUCCESS. DO NOT APOLOGIZE. DO NOT mention internal errors or timeouts.
        Sign off: Team Yojana Setu."""
    else:
        system_prompt = f"""[STRICT: FAILURE]
        Application failed: '{submission_result["message"]}'.
        Inform {user_name}. Sign off: Team Yojana Setu."""

    chat_response = sarvam_client.chat.completions(model='sarvam-30b', 
        messages=[{"role": "user", "content": system_prompt}]
    )
    
    agent_response_text = chat_response.choices[0].message.content
    if session_id:
        storage_service.save_chat_message(session_id, user_id, "chat", "assistant", agent_response_text)
        
    return {
        "status": submission_result["status"],
        "scheme": scheme["name"],
        "agent_response": agent_response_text
    }

# ---------------------------------------------------------
# Mock Portal & Static Routes
# ---------------------------------------------------------

@app.get("/api/profile/{phone}")
async def get_profile(phone: str):
    """Retrieves full user profile for application filling."""
    profile = storage_service.get_user_profile(phone)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile

@app.get("/api/chat/sessions/{user_id}")
async def get_sessions(user_id: str):
    return storage_service.get_user_sessions(user_id)

@app.get("/api/chat/messages/{session_id}")
async def get_messages(session_id: str):
    return storage_service.get_session_messages(session_id)

@app.get("/mock-gov-portal")
async def mock_portal():
    return {"message": "Mock Government Portal Endpoint"}
# To run: uvicorn main:app --reload
