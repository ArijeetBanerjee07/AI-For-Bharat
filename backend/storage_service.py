import os
import json
import boto3
import time
from datetime import datetime
from dotenv import load_dotenv, find_dotenv

# Search parent dirs for .env if needed
dotenv_file = find_dotenv()
if dotenv_file:
    load_dotenv(dotenv_file)
else:
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

class StorageService:
    def __init__(self):
        # In-memory fallbacks for offline / local / invalid AWS credential modes
        self.memory_profiles = {}
        self.memory_sessions = {}  # session_id -> item
        self.memory_messages = {}  # session_id -> list of msg dicts

        self.dynamodb = None
        self.user_table = None
        self.sessions_table = None
        self.messages_table = None
        
        # AWS DynamoDB Setup
        aws_id = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret = os.getenv('AWS_SECRET_ACCESS_KEY')
        
        if aws_id and aws_secret:
            try:
                self.dynamodb = boto3.resource(
                    'dynamodb',
                    aws_access_key_id=aws_id,
                    aws_secret_access_key=aws_secret,
                    region_name=os.getenv('AWS_REGION', 'ap-south-1')
                )
                self.user_table_name = os.getenv('DYNAMODB_TABLE_NAME', 'user_profiles')
                self.sessions_table_name = 'chat_sessions'
                self.messages_table_name = 'chat_messages'

                self.user_table = self.dynamodb.Table(self.user_table_name)
                self.sessions_table = self.dynamodb.Table(self.sessions_table_name)
                self.messages_table = self.dynamodb.Table(self.messages_table_name)
                print(f"📦 Cloud Storage Service Initialized (DynamoDB: {self.user_table_name})")
            except Exception as e:
                print(f"⚠️ Cloud Storage AWS Init warning: {e}. Falling back to in-memory storage.")
        else:
            print("ℹ️ AWS credentials not found. Operating with in-memory storage mode.")

    def get_user_sessions(self, user_id):
        """Retrieves all chat sessions for a specific user."""
        print(f"🔍 Fetching sessions for user_id: {user_id}")
        print(f"   Memory sessions total: {len(self.memory_sessions)}")
        
        if self.sessions_table:
            try:
                from boto3.dynamodb.conditions import Key
                # Use GSI for efficient querying by user_id
                response = self.sessions_table.query(
                    IndexName='user_id_updated_at_index',
                    KeyConditionExpression=Key('user_id').eq(user_id),
                    ScanIndexForward=False  # Sort by updated_at descending
                )
                items = response.get('Items', [])
                print(f"✅ Retrieved {len(items)} sessions from DynamoDB for user {user_id}")
                return items
            except Exception as e:
                print(f"⚠️ DynamoDB get_user_sessions error: {e}. Using memory fallback.")

        # Memory fallback
        user_sess = [s for s in self.memory_sessions.values() if s.get('user_id') == user_id]
        user_sess.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
        print(f"✅ Retrieved {len(user_sess)} sessions from memory for user {user_id}")
        print(f"   Sessions: {[s.get('title') for s in user_sess]}")
        return user_sess

    def get_session_messages(self, session_id):
        """Retrieves all messages for a specific session."""
        if self.messages_table:
            try:
                from boto3.dynamodb.conditions import Key
                response = self.messages_table.query(
                    KeyConditionExpression=Key('session_id').eq(session_id)
                )
                items = response.get('Items', [])
                items.sort(key=lambda x: x.get('created_at', ''))
                return [{"role": item["role"], "content": item["content"]} for item in items]
            except Exception as e:
                print(f"⚠️ DynamoDB get_session_messages error: {e}. Using memory fallback.")

        # Memory fallback
        msgs = self.memory_messages.get(session_id, [])
        msgs.sort(key=lambda x: x.get('created_at', ''))
        return [{"role": item["role"], "content": item["content"]} for item in msgs]

    def save_chat_message(self, session_id, user_id, title, role, content):
        """Saves a chat message and updates session metadata."""
        now = datetime.now().isoformat()
        message_id = f"{session_id}_{int(time.time() * 1000)}"
        
        print(f"💾 Saving message: session_id={session_id}, user_id={user_id}, role={role}, title={title[:30]}...")

        # Memory save (always update memory as cache)
        self.memory_sessions[session_id] = {
            'session_id': session_id,
            'user_id': user_id,
            'title': title,
            'updated_at': now
        }
        if session_id not in self.memory_messages:
            self.memory_messages[session_id] = []
        self.memory_messages[session_id].append({
            'session_id': session_id,
            'created_at': now,
            'role': role,
            'content': content,
            'message_id': message_id
        })
        print(f"✅ Message saved to memory. Total sessions in memory: {len(self.memory_sessions)}")

        if self.sessions_table and self.messages_table:
            try:
                self.sessions_table.put_item(
                    Item={
                        'session_id': session_id,
                        'user_id': user_id,
                        'title': title,
                        'updated_at': now
                    }
                )
                self.messages_table.put_item(
                    Item={
                        'session_id': session_id,
                        'created_at': now,
                        'role': role,
                        'content': content,
                        'message_id': message_id
                    }
                )
                print(f"✅ Message saved to DynamoDB")
            except Exception as e:
                print(f"⚠️ DynamoDB save_chat_message warning: {e}. Message saved to in-memory fallback.")

    def get_user_profile(self, phone_number):
        """Retrieves user profile."""
        if self.user_table:
            try:
                response = self.user_table.get_item(Key={'user_id': phone_number})
                item = response.get('Item')
                if item:
                    return item
            except Exception as e:
                print(f"⚠️ DynamoDB get_user_profile warning: {e}. Using memory fallback.")

        return self.memory_profiles.get(phone_number, {})

    def save_user_profile(self, profile):
        """Saves/Updates user profile."""
        user_id = profile.get('user_id') or profile.get('phone')
        if not user_id:
            print("❌ Cannot save profile: No user_id/phone found.")
            return False
            
        profile['user_id'] = user_id
        self.memory_profiles[user_id] = profile

        if self.user_table:
            try:
                self.user_table.put_item(Item=profile)
                return True
            except Exception as e:
                print(f"⚠️ DynamoDB save_user_profile warning: {e}. Profile saved in-memory.")
                return True

        return True

    def upload_to_s3(self, file_content, file_name, content_type='audio/mpeg'):
        """Uploads audio/images to S3 for processing."""
        aws_id = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret = os.getenv('AWS_SECRET_ACCESS_KEY')
        bucket = os.getenv('S3_BUCKET_NAME')
        if not (aws_id and aws_secret and bucket):
            return None

        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_id,
                aws_secret_access_key=aws_secret,
                region_name=os.getenv('AWS_REGION', 'ap-south-1')
            )
            s3_client.put_object(
                Bucket=bucket,
                Key=file_name,
                Body=file_content,
                ContentType=content_type
            )
            return f"s3://{bucket}/{file_name}"
        except Exception as e:
            print(f"⚠️ Error uploading to S3: {e}")
            return None
