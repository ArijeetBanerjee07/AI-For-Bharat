from agent_service import AgentService
import json

def verify():
    print("--- Starting AgentService Verification ---")
    agent = AgentService()
    
    user_message = "Namaste, can you tell me about PM Awas Yojana?"
    user_profile = {
        "username": "Test User",
        "phone": "9876543210"
    }
    
    print(f"Sending message: {user_message}")
    try:
        reply = agent.chat(user_message, [], user_profile)
        print("\nAI REPLY RECEIVED:")
        print("-" * 30)
        print(reply)
        print("-" * 30)
        
        if "Awas" in reply or "PM" in reply or "yojana" in reply.lower():
            print("\nSUCCESS: Bedrock is responding correctly!")
        else:
            print("\nWARNING: Received a response, but it might not be the expected content.")
            
    except Exception as e:
        print(f"\nFAILURE: Verification failed with error: {str(e)}")

if __name__ == "__main__":
    verify()
