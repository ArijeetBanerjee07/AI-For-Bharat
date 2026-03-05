import boto3
import os
import json
from dotenv import load_dotenv

load_dotenv()

class AgentService:
    def __init__(self):
        # Bedrock Configuration
        self.primary_region = os.getenv('AWS_REGION', 'ap-south-1')
        self.secondary_region = 'us-east-1' # Better model availability for fallbacks
        self.model_id = os.getenv('BEDROCK_MODEL_ID', 'anthropic.claude-3-5-sonnet-20241022-v2:0')
        
        # AWS Credentials
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')

        # Clients for different regions to ensure high availability
        self.primary_client = boto3.client(
            service_name='bedrock-runtime',
            region_name=self.primary_region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        
        self.secondary_client = boto3.client(
            service_name='bedrock-runtime',
            region_name=self.secondary_region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )

    def chat(self, user_message, conversation_history=[], user_profile={}):
        """
        AI Interaction using Amazon Bedrock (Amazon Nova Lite / Micro Fallback)
        """
        SCHEME_REQUIREMENTS = {
            "PM Awas Yojana": ["aadhar", "income", "land_status"],
            "PM Kisan": ["aadhar", "farmer_id", "bank_account"],
            "Ladli Behna": ["aadhar", "samagra_id", "bank_account"],
            "Swasthya Sathi": ["aadhar", "ration_card", "family_count"],
            "Old Age Pension": ["aadhar", "age_proof", "bank_ifsc"]
        }

        system_prompt = f"""
        You are 'Yojna Setu', a high-intent AI caseworker for rural India.
        Your goal is to get a user applied for a specific government scheme.
        
        CURRENT USER PROFILE:
        {json.dumps(user_profile, indent=2)}
        
        SCHEME KNOWLEDGE BASE:
        {json.dumps(SCHEME_REQUIREMENTS, indent=2)}
        
        STRICT OPERATING RULES:
        1. Language: Use Hinglish (Hindi + English).
        2. Selection: If the user doesn't specify a scheme, list the 5 schemes available and ask which one they want.
        3. Proactiveness: Once a scheme is chosen:
           - Cross-reference the PROFILE with the SCHEME KNOWLEDGE BASE.
           - Ask for EXACTLY the missing fields for THAT scheme (e.g., if it's PM Kisan, ask for Farmer ID).
           - Do NOT ask for everything at once if you already have some details.
        4. Action Trigger: ONLY when you have ALL required fields for the chosen scheme, you MUST apply.
           - To apply, FIRST provide a polite verbal confirmation of what you are doing (e.g. "Theek hai ji, mujhe sab mil gaya hai. Main ab application bhar raha hoon..."), then append exactly: `[ACTION: OPEN_PORTAL | scheme: <scheme_name> | details: <json_of_all_fields>]`
        5. Tone: Polite, caseworker-like, and efficient.
        """

        # Convert conversation history
        messages = []
        for msg in conversation_history:
            role = msg.get('role')
            content = msg.get('content')
            if role not in ['user', 'assistant']: continue
            if isinstance(content, str): content_blocks = [{"text": content}]
            elif isinstance(content, list): content_blocks = content if content and 'text' in content[0] else [{"text": str(content)}]
            else: content_blocks = [{"text": str(content)}]
            messages.append({"role": role, "content": content_blocks})

        messages.append({"role": "user", "content": [{"text": user_message}]})

        # --- Nova Fallback Strategy ---
        # Prioritize the configured ID (apac.amazon.nova-lite-v1:0)
        model_options = [
            self.model_id,
            "apac.amazon.nova-lite-v1:0",
            "apac.amazon.nova-micro-v1:0",
            "amazon.nova-lite-v1:0",
            "amazon.nova-micro-v1:0"
        ]

        # Filter duplicates while preserving order
        seen = set()
        unique_models = [x for x in model_options if not (x in seen or seen.add(x))]

        for m_id in unique_models:
            print(f"--- Calling Bedrock: {m_id} ---")
            response = self._try_model(self.primary_client, m_id, messages, system_prompt)
            if response: return response

        return "Maaf kijiye, hamare AI system mein thodi takleef ho rahi hai. Kripya thodi der baad koshish karein. (Nova Service Busy)"

    def _try_model(self, client, model_id, messages, system):
        """
        Helper to try a specific Bedrock model with the Converse API.
        """
        try:
            response = client.converse(
                modelId=model_id,
                messages=messages,
                system=[{"text": system}],
                inferenceConfig={'maxTokens': 1000, 'temperature': 0.7}
            )
            return response['output']['message']['content'][0]['text']
        except Exception as e:
            print(f"!!! Bedrock {model_id} failed: {str(e)}")
            return None

    def apply_for_scheme(self, user_phone, scheme_name, user_info):
        """
        Mock function to 'Apply' for a scheme on behalf of the user.
        In a real scenario, this would call a government API or fill a form.
        """
        application_id = f"APP-{os.urandom(4).hex().upper()}"
        print(f"Applying for {scheme_name} for user {user_phone}...")
        return {
            "status": "Success",
            "application_id": application_id,
            "message": f"Aapka {scheme_name} ke liye aavedan (application) submit ho gaya hai. Reference ID: {application_id}"
        }

