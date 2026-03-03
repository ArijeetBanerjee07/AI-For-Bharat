import os
import json
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder

load_dotenv()

app = FastAPI(title="Yojana-Setu Phygital Backend")

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
    system_prompt = f"""You are a helpful, empathetic "Phygital" caseworker for Yojana-Setu, assisting rural citizens in India.
Your goal is to answer their questions about government schemes clearly and simply.

You MUST base your answer ONLY on the following official guidelines and facts provided. 
If the answer is not in the facts, say you don't have that information.
Do not use jargon.

Here are the facts you must use:
{context_string}
"""

    return StreamingResponse(
        get_sarvam_stream(system_prompt, user_query), 
        media_type="text/event-stream"
    )

# To run: uvicorn main:app --reload