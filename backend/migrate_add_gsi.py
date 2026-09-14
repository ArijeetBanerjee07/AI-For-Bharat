"""
Migration script to add user_id GSI to existing chat_sessions table.
This script updates the chat_sessions table to include a Global Secondary Index
for efficient querying of sessions by user_id.
"""
import boto3
import os
import time
from dotenv import load_dotenv

load_dotenv()

def migrate_add_user_id_gsi():
    # Initialize DynamoDB resource
    dynamodb = boto3.resource(
        'dynamodb',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION', 'ap-south-1')
    )

    table_name = 'chat_sessions'
    
    try:
        table = dynamodb.Table(table_name)
        
        # Get current table info
        table.load()
        current_gsis = [gsi['IndexName'] for gsi in table.global_secondary_indexes or []]
        
        if 'user_id_updated_at_index' in current_gsis:
            print(f"✅ GSI 'user_id_updated_at_index' already exists on table '{table_name}'")
            return
        
        print(f"⏳ Adding GSI 'user_id_updated_at_index' to table '{table_name}'...")
        
        # Update table to add GSI
        table.update(
            GlobalSecondaryIndexUpdates=[
                {
                    'Create': {
                        'IndexName': 'user_id_updated_at_index',
                        'KeySchema': [
                            {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                            {'AttributeName': 'updated_at', 'KeyType': 'RANGE'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'ProvisionedThroughput': {
                            'ReadCapacityUnits': 5,
                            'WriteCapacityUnits': 5
                        }
                    }
                }
            ]
        )
        
        # Wait for GSI to be created (can take a few minutes)
        print("⏳ Waiting for GSI to be created (this may take 1-5 minutes)...")
        waiter = dynamodb.meta.client.get_waiter('table_exists')
        
        # Check GSI creation status periodically
        for attempt in range(60):  # Try for up to 5 minutes (60 * 5 seconds)
            try:
                table.reload()
                gsies = table.global_secondary_indexes or []
                for gsi in gsies:
                    if gsi['IndexName'] == 'user_id_updated_at_index':
                        status = gsi['IndexStatus']
                        if status == 'ACTIVE':
                            print(f"✅ GSI 'user_id_updated_at_index' is now ACTIVE!")
                            return
                        else:
                            print(f"   Current status: {status} (attempt {attempt + 1}/60)")
            except Exception as e:
                print(f"   Checking status... ({attempt + 1}/60)")
            
            time.sleep(5)
        
        print("⚠️ GSI creation is in progress but taking longer than expected.")
        print("   You can check the status in AWS Console > DynamoDB > Tables > chat_sessions")
        
    except Exception as e:
        print(f"❌ Error migrating table: {e}")
        print("\nFALLBACK: If you prefer to recreate the table:")
        print("1. Delete the existing 'chat_sessions' table in AWS Console")
        print("2. Run: python backend/setup_dynamodb.py")

if __name__ == "__main__":
    migrate_add_user_id_gsi()
