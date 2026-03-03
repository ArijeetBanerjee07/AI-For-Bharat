import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder

# 1. Load Models
# Bi-Encoder (Stage 1: Fast Search)
bi_encoder = SentenceTransformer('all-MiniLM-L6-v2')
# Cross-Encoder (Stage 3: High-Accuracy Reranking)
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

# 2. Connect to Chroma
chroma_client = chromadb.PersistentClient(path="./yojana_setu_db")
collection = chroma_client.get_collection(name="government_schemes")

def high_quality_search(query, fetch_k=20, top_n=3):
    # Step 1: Semantic Search (fetch_k results)
    query_embedding = bi_encoder.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=fetch_k  # Grab a larger pool first
    )
    
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
    return reranked_results[:top_n]

if __name__ == "__main__":
    query = "How can a farmer apply for housing?"
    final_hits = high_quality_search(query)

    print("\n🚀 Reranked High-Quality Results:")
    for doc, meta, score in final_hits:
        print(f"\n[Score: {score:.4f}] Scheme: {meta.get('scheme_name', 'Unknown')}")
        print(f"Content: {doc[:200]}...")