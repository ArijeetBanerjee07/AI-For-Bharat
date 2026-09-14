export const API_BASE_URL = 
    process.env.NEXT_PUBLIC_API_URL || 
    (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'
        ? 'https://ai-for-bharat-backend.onrender.com'
        : 'http://127.0.0.1:8000');

