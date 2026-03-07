import os
import json
import time
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

# 1. Initialize the local model
# 'all-MiniLM-L6-v2' is fast, lightweight, and perfect for a MacBook Air.
# It produces 384-dimensional embeddings.
print("Loading local embedding model...")
model = SentenceTransformer('all-MiniLM-L6-v2')

# 2. Initialize Pinecone
pinecone_api_key = os.getenv("PINECONE_API_KEY")
if not pinecone_api_key:
    raise ValueError("PINECONE_API_KEY is not set in .env")

pc = Pinecone(api_key=pinecone_api_key)
index_name = "yojana-setu"

def get_or_create_index():
    existing_indexes = pc.list_indexes().names()
    if index_name not in existing_indexes:
        print(f"Creating Pinecone index '{index_name}'...")
        pc.create_index(
            name=index_name,
            dimension=384,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        # Wait for index to be ready
        while not pc.describe_index(index_name).status['ready']:
            time.sleep(1)
        print(f"Index '{index_name}' created successfully.")
    return pc.Index(index_name)

index = get_or_create_index()

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
            
            # Batch upsert to Pinecone
            batch_size = 100
            for i in range(0, len(chunks_data), batch_size):
                batch = chunks_data[i:i + batch_size]
                
                # Fetch existing IDs in the batch to avoid duplicates
                # Pinecone fetch allows retrieving by IDs
                ids_to_check = [chunk["chunk_id"] for chunk in batch]
                existing = index.fetch(ids=ids_to_check)
                existing_ids = set(existing.vectors.keys())
                
                upsert_data = []
                for chunk in batch:
                    chunk_id = chunk["chunk_id"]
                    if chunk_id in existing_ids:
                        continue
                        
                    content = chunk["content"]
                    metadata = chunk["metadata"]
                    # Store content in metadata so we can retrieve it
                    metadata["content"] = content
                    
                    # 3. Generate embedding locally
                    embedding = model.encode(content).tolist()
                    
                    upsert_data.append((chunk_id, embedding, metadata))
                
                if upsert_data:
                    # 4. Store in Pinecone
                    index.upsert(vectors=upsert_data)
                    print(f"Upserted {len(upsert_data)} vectors from batch {i//batch_size + 1}")
            
            print(f"✅ Successfully processed {filename}.")

if __name__ == "__main__":
    process_and_store_chunks()