# Yojana-Setu: Project Requirements

## Project Overview
**Project Name**: Yojana-Setu (Scheme-Bridge)  
**Tagline**: The Voice-First AI Caseworker for Rural India  
**Target**: AI for Bharat Hackathon Submission  

## Problem Statement
1. **Information Gap**: 70% of eligible citizens don't know which government schemes exist
2. **Middleman Dependency**: Rural citizens pay Rs.500-2000 to local agents for form-filling
3. **High Rejection Rates**: 40% of applications rejected due to preventable errors

**Target**: 800 million rural Indians eligible for government schemes

## Core Features
1. **Multi-Channel Access**: WhatsApp Bot, IVR system, Web dashboard
2. **Voice-First Interaction**: Hindi/regional languages, code-mixed speech support
3. **Intelligent Scheme Discovery**: Proactive matching, eligibility assessment
4. **Document Processing**: Real-time verification, OCR, quality checks
5. **Application Management**: End-to-end assistance, status tracking

## Technical Requirements

### AWS Services (Premium Implementation)
- **Amazon Bedrock**: Claude 3.5 Sonnet for reasoning
- **Amazon Q Business**: Knowledge base for schemes
- **Amazon Transcribe**: Voice-to-text conversion
- **Amazon Polly**: Text-to-speech responses
- **AWS Lambda**: Core orchestration logic
- **Amazon DynamoDB**: User profiles and data
- **Amazon S3**: Document storage

### Low-Cost Implementation Stack
#### AI and ML (5 services)
- **Pinecone**: RAG knowledge base (Free)
- **TesseractOCR**: Document OCR (Open-source)
- **Whisper**: Speech-to-text (Free)
- **gTTS**: Text-to-speech (Free)
- **Ollama + Llama 3**: Local LLM (Free)

#### Backend (3 services)
- **Railway/Vercel**: Serverless compute (Free tier)
- **Supabase**: Database (Free tier: 500MB)
- **FastAPI**: REST API (Open-source)

#### Communication (3 services)
- **WhatsApp Cloud API**: 1000 messages/month free
- **Twilio Trial**: IVR for feature phones
- **Twilio SMS**: Notifications

#### Frontend (4 technologies)
- **Next.js 14**: Web framework
- **React**: UI components
- **TypeScript**: Type safety
- **Tailwind CSS**: Styling

## Cost Breakdown
- **MVP (0-1K users)**: Rs.0-500/month (Free tiers)
- **Scale (1K-10K users)**: Rs.7,500/month
- **Growth (10K-100K users)**: Rs.46,000/month

## Hackathon Deliverables
1. **Functional Prototype**: WhatsApp simulator with voice/document processing
2. **GitHub Repository**: Complete codebase with documentation
3. **Video Pitch**: 3-minute demo (Problem-Solution-Impact)
4. **Technical Blog**: 1500+ words on AWS Builder Center
5. **Presentation**: 10-12 slides covering architecture and impact

## Success Criteria
### Judging Alignment
- **Creativity (30%)**: Novel "Phygital" approach, proactive AI agent
- **Technical (30%)**: 10+ AWS services, multimodal AI, production-ready
- **Impact (25%)**: 800M beneficiaries, measurable outcomes
- **Presentation (15%)**: Working prototype, comprehensive docs

### KPIs
- **User Adoption**: 10K users in pilot
- **Cost Savings**: Rs.50L saved for citizens
- **Rejection Reduction**: 40% to 10%
- **Time Savings**: 2 hours to 15 minutes per application

## User Stories
**Rural Farmer**: "I want to speak in my language, discover eligible schemes, and submit documents via phone camera"

**Illiterate Citizen**: "I want voice-only interaction with step-by-step guidance on my basic phone"

**Government Official**: "I want reduced rejection rates and increased scheme uptake"

## Implementation Phases
- **Phase 1 (Rs.0)**: MVP with free tiers, 5 schemes, WhatsApp simulator
- **Phase 2 (Rs.7,500/month)**: Real integrations, 20+ schemes, basic analytics
- **Phase 3 (Rs.46,000/month)**: Multi-language, 100+ schemes, government partnerships

## Revenue Model
- Government contracts (Rs.10-50L per state)
- CSC partnerships
- White-label licensing
- Premium analytics features

## Future Roadmap
1. Pilot in 2 districts
2. State government partnerships  
3. National rollout with 10+ languages