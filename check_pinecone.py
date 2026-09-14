import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()
pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
try:
    stats = pc.Index('yojana-setu').describe_index_stats()
    desc = pc.describe_index('yojana-setu')
    print(f"Stats: {stats}")
    print(f"Dimension: {desc.dimension}")
except Exception as e:
    print(f"Error: {e}")
