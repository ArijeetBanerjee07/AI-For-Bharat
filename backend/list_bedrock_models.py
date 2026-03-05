import boto3
import os
from dotenv import load_dotenv

load_dotenv()

def list_models():
    print("--- Listing Anthropic Models in ap-south-1 (Mumbai) ---")
    try:
        bedrock = boto3.client(
            'bedrock',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name='ap-south-1'
        )
        
        response = bedrock.list_foundation_models()
        all_models = response['modelSummaries']
        
        for m in all_models:
            print(f"ID: {m['modelId']} | Name: {m['modelName']}")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    list_models()
