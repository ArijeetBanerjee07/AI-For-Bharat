import os
from pinecone import Pinecone
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, CrossEncoder

load_dotenv()

# 1. Load Models
# Bi-Encoder (Stage 1: Fast Search)
bi_encoder = SentenceTransformer('all-MiniLM-L6-v2')
# Cross-Encoder (Stage 3: High-Accuracy Reranking)
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

# 2. Connect to Pinecone
pinecone_api_key = os.getenv("PINECONE_API_KEY")
pc = Pinecone(api_key=pinecone_api_key)
index_name = "yojana-setu"
index = pc.Index(index_name)

def high_quality_search(query, fetch_k=20, top_n=3):
    # Step 1: Semantic Search (fetch_k results)
    query_embedding = bi_encoder.encode(query).tolist()
    
    # Query Pinecone
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
        # We stored the text inside metadata['content']
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
    return reranked_results[:top_n]

if __name__ == "__main__":
    query = "How can a farmer apply for housing?"
    final_hits = high_quality_search(query)

    print("\n🚀 Reranked High-Quality Results:")
    for doc, meta, score in final_hits:
        print(f"\n[Score: {score:.4f}] Scheme: {meta.get('scheme_name', 'Unknown')}")
        print(f"Content: {doc[:200]}...")