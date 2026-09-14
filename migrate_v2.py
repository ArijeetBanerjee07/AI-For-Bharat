import os
import time
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv()
pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))

index_name = "yojana-setu-v2"

# 1. Create Index if not exists
if index_name not in pc.list_indexes().names():
    print(f"Creating index {index_name} (1024 dims)...")
    pc.create_index(
        name=index_name,
        dimension=1024,
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",
            region="us-east-1"
        )
    )
    print("Waiting for index to be ready...")
    while not pc.describe_index(index_name).status['ready']:
        time.sleep(1)

print(f"Index {index_name} is ready!")
index = pc.Index(index_name)

# 2. Prepare Data
from langchain_text_splitters import RecursiveCharacterTextSplitter

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=600,
    chunk_overlap=50,
)

data_dir = os.path.join("backend", "data", "markdowns")
markdown_files = [f for f in os.listdir(data_dir) if f.endswith(".md")]

all_vectors = []
vector_id = 0

print(f"Reading {len(markdown_files)} files...")
for filename in markdown_files:
    path = os.path.join(data_dir, filename)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    chunks = text_splitter.split_text(content)
    print(f" - {filename}: {len(chunks)} chunks")
    
    # Batch embedding
    for chunk in chunks:
        # We'll batch these later or just do them one by one for simplicity in this script
        res = pc.inference.embed(
            model="multilingual-e5-large",
            inputs=[chunk],
            parameters={"input_type": "passage"}
        )
        
        all_vectors.append({
            "id": str(vector_id),
            "values": res[0].values,
            "metadata": {
                "content": chunk,
                "document": filename
            }
        })
        vector_id += 1

# 3. Upsert
print(f"Upserting {len(all_vectors)} vectors...")
# Standard batch size for Pinecone upserts
for i in range(0, len(all_vectors), 100):
    batch = all_vectors[i:i+100]
    index.upsert(vectors=batch)

print("Migration Complete! 🚀")
