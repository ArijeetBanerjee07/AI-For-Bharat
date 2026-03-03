import os
import json
import chromadb
from sentence_transformers import SentenceTransformer

# 1. Initialize the local model
# 'all-MiniLM-L6-v2' is fast, lightweight, and perfect for a MacBook Air.
# It produces 384-dimensional embeddings.
print("Loading local embedding model...")
model = SentenceTransformer('all-MiniLM-L6-v2')

# 2. Initialize ChromaDB
chroma_client = chromadb.PersistentClient(path="./yojana_setu_db")
collection = chroma_client.get_or_create_collection(name="government_schemes")

def process_and_store_chunks(chunks_dir="data/chunks"):
    # Ensure the directory exists
    if not os.path.exists(chunks_dir):
        print(f"Error: Directory {chunks_dir} not found.")
        return

    for filename in os.listdir(chunks_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(chunks_dir, filename)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                chunks_data = json.load(f)
            
            print(f"Processing {filename} ({len(chunks_data)} chunks)...")
            
            for chunk in chunks_data:
                chunk_id = chunk["chunk_id"]
                content = chunk["content"]
                metadata = chunk["metadata"]

                # Check if already exists to avoid redundant work
                existing = collection.get(ids=[chunk_id])
                if existing['ids']:
                    continue
                
                # 3. Generate embedding locally (No more AWS Throttling!)
                embedding = model.encode(content).tolist()
                
                # 4. Store in ChromaDB
                collection.upsert(
                    ids=[chunk_id],
                    embeddings=[embedding],
                    documents=[content],
                    metadatas=[metadata]
                )
            
            print(f"✅ Successfully stored {filename} in Vector DB.")

if __name__ == "__main__":
    process_and_store_chunks()