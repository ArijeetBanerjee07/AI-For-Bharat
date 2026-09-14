'use client';

import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useSearchParams, useRouter } from 'next/navigation';
import { API_BASE_URL } from '@/lib/constants';


interface Message {
    role: 'user' | 'assistant' | 'system';
    content: string;
}

export default function ChatPage() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [userPhone, setUserPhone] = useState<string | null>(null);
    const [userName, setUserName] = useState<string | null>(null);
    const [detectedScheme, setDetectedScheme] = useState<string | null>(null);
    const [requiredDocs, setRequiredDocs] = useState<string[]>([]);
    const [showPortal, setShowPortal] = useState(false);
    const [portalUrl, setPortalUrl] = useState('/mock-gov/index.html');
    const [isRecording, setIsRecording] = useState(false);
    const [sessionId, setSessionId] = useState<string>('');

    const router = useRouter();

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);

    useEffect(() => {
        // Ping backend silently to wake up Render container if sleeping
        fetch(`${API_BASE_URL}/`).catch(() => {});

        const phone = localStorage.getItem('user_phone');
        const name = localStorage.getItem('user_name');
        const fallbackName = name ? name : "Guest";
        
        console.log('💬 Chat page loaded - phone:', phone, 'name:', name);

        const params = new URLSearchParams(window.location.search);
        let currentSessionId = params.get('session_id');

        const welcomeMessage: Message = {
            role: 'assistant',
            content: `Namasta ${fallbackName}! Main Yojana-Setu AI hoon. Main aapki sarkari yojanaon ke baare mein jaankari dene aur aavedan (apply) karne mein madad kar sakta hoon.`
        };

        if (!currentSessionId) {
            currentSessionId = `sess_${Math.random().toString(36).substring(2, 9)}_${Date.now()}`;
            console.log('🆕 New session created:', currentSessionId);
            setSessionId(currentSessionId);
            setMessages([welcomeMessage]);
            router.replace(`/chat?session_id=${currentSessionId}`);
        } else {
            console.log('📂 Existing session found:', currentSessionId);
            setSessionId(currentSessionId);
            // Fetch existing messages
            fetch(`${API_BASE_URL}/api/chat/messages/${currentSessionId}`)
                .then(res => {
                    if (!res.ok) throw new Error("Fetch failed");
                    return res.json();
                })
                .then(data => {
                    if (Array.isArray(data) && data.length > 0) {
                        console.log('✅ Loaded', data.length, 'messages from session');
                        setMessages(data as Message[]);
                    } else {
                        // Empty session from DB, show welcome!
                        console.log('📭 Empty session, showing welcome message');
                        setMessages([welcomeMessage]);
                    }
                })
                .catch(err => {
                    console.error("❌ Failed to load chat:", err);
                    setMessages([welcomeMessage]);
                });
        }

        if (phone && name) {
            setUserPhone(phone);
            setUserName(name);
        } else {
            setUserPhone('9876543210');
            setUserName('Guest User');
        }
    }, [router]);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    useEffect(() => {
        if (detectedScheme === 'pmjdy') {
            setPortalUrl('/mock-pmjdy/index.html');
        } else {
            setPortalUrl('/mock-gov/index.html');
        }
    }, [detectedScheme]);

    useEffect(() => {
        const handleWindowMessage = (event: MessageEvent) => {
            if (event.data && event.data.type === 'PORTAL_READY') {
                if (lastPortalMsgRef.current) {
                    const iframe = iframeRef.current || (document.querySelector('iframe') as HTMLIFrameElement);
                    if (iframe && iframe.contentWindow) {
                        iframe.contentWindow.postMessage(lastPortalMsgRef.current, '*');
                    }
                }
            }
        };

        window.addEventListener('message', handleWindowMessage);
        return () => window.removeEventListener('message', handleWindowMessage);
    }, []);

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            audioChunksRef.current = [];
            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) audioChunksRef.current.push(event.data);
            };
            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
                handleVoiceMessage(audioBlob);
                stream.getTracks().forEach(track => track.stop());
            };
            mediaRecorder.start();
            setIsRecording(true);
        } catch (err) {
            console.error("Mic access denied:", err);
        }
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current && isRecording) {
            mediaRecorderRef.current.stop();
            setIsRecording(false);
        }
    };

    const handleVoiceMessage = async (audioBlob: Blob) => {
        setIsLoading(true);
        setMessages(prev => [...prev, { role: 'user', content: "🎙️ Processing voice..." }, { role: 'assistant', content: '' }]);

        try {
            const formData = new FormData();
            formData.append('audio', audioBlob, 'voice.webm');
            formData.append('user_name', userName || "Citizen");
            formData.append('user_id', userPhone || "9876543210");
            if (detectedScheme) formData.append('scheme_id', detectedScheme);

            const response = await fetch(`${API_BASE_URL}/api/voice-agent`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(`Server returned status ${response.status}`);
            }

            const data = await response.json();
            setMessages(prev => {
                const newMessages = [...prev];
                newMessages[newMessages.length - 2] = { role: 'user', content: `🎙️ ${data.user_text}` };
                newMessages[newMessages.length - 1] = { role: 'assistant', content: data.agent_text };
                return newMessages;
            });

            if (data.audio_base64) {
                const audio = new Audio(`data:audio/mp3;base64,${data.audio_base64}`);
                audio.play();
            }
        } catch (error) {
            console.error('Voice Error:', error);
            setMessages(prev => {
                const newMessages = [...prev];
                newMessages[newMessages.length - 1] = { 
                    role: 'assistant', 
                    content: '⚠️ Voice processing server error. Backend may be waking up from sleep. Please try again in a few seconds.' 
                };
                return newMessages;
            });
        } finally {
            setIsLoading(false);
        }
    };

    const iframeRef = useRef<HTMLIFrameElement>(null);
    const lastPortalMsgRef = useRef<any>(null);

    const sendPortalMessage = (msg: any) => {
        lastPortalMsgRef.current = msg;
        const iframe = iframeRef.current || (document.querySelector('iframe') as HTMLIFrameElement);
        if (iframe && iframe.contentWindow) {
            iframe.contentWindow.postMessage(msg, '*');
        }
    };

    const handleIframeLoad = () => {
        if (lastPortalMsgRef.current) {
            const iframe = iframeRef.current || (document.querySelector('iframe') as HTMLIFrameElement);
            if (iframe && iframe.contentWindow) {
                iframe.contentWindow.postMessage(lastPortalMsgRef.current, '*');
            }
        }
    };

    const handleSendMessage = async (e: React.FormEvent) => {
        e.preventDefault();
        if ((!input.trim() && selectedFiles.length === 0) || isLoading) return;

        const userMessage = input.trim();
        const filesToSend = [...selectedFiles];
        setInput('');
        setSelectedFiles([]);

        let displayContent = userMessage;
        if (filesToSend.length > 0) {
            displayContent += `\n\n${filesToSend.map(f => `📎 *${f.name}*`).join('\n')}`;
            // If files are sent, we are likely applying. Show portal.
            setShowPortal(true);

            // Fetch initial profile for instant preview auto-fill while backend processes OCR
            fetch(`${API_BASE_URL}/api/profile/${userPhone || "9876543210"}`)
                .then(res => res.json())
                .then(profile => {
                    if (profile && !profile.detail) {
                        sendPortalMessage({ type: 'AUTO_FILL', payload: profile });
                    }
                })
                .catch(e => console.error("Could not fetch profile for preview auto-fill", e));
        }

        setMessages(prev => [...prev, { role: 'user', content: displayContent }, { role: 'assistant', content: '' }]);
        setIsLoading(true);

        try {
            const formData = new FormData();
            formData.append('user_text', userMessage || "Evaluating documents...");
            formData.append('user_name', userName || "Citizen");
            formData.append('user_id', userPhone || "9876543210");
            if (sessionId) formData.append('session_id', sessionId);

            if (filesToSend.length > 0) {
                filesToSend.forEach(file => formData.append('documents', file));
                if (detectedScheme) formData.append('scheme_id', detectedScheme);
                if (requiredDocs.length > 0) formData.append('doc_types', requiredDocs.join(','));
            }

            const response = await fetch(`${API_BASE_URL}/api/agent`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(`Server returned status ${response.status}`);
            }

            const contentType = response.headers.get('content-type') || '';

            if (contentType.includes('application/json')) {
                const data = await response.json();
                if (data.scheme_id) setDetectedScheme(data.scheme_id);
                if (data.required_docs) setRequiredDocs(data.required_docs);

                // Show portal if an action is required or taking place
                if (data.action === 'upload_documents' || data.status === 'success' || data.user_data) {
                    setShowPortal(true);
                }

                if (data.status === 'success' || data.user_data) {
                    const portalMsg = {
                        type: 'AUTO_FILL_AND_SUBMIT',
                        payload: data.user_data || {},
                        ref_number: data.ref_number
                    };
                    
                    sendPortalMessage(portalMsg);
                    setTimeout(() => sendPortalMessage(portalMsg), 400);
                    setTimeout(() => sendPortalMessage(portalMsg), 1200);
                }

                setMessages(prev => {
                    const newMessages = [...prev];
                    newMessages[newMessages.length - 1] = { role: 'assistant', content: data.response || data.agent_response };
                    return newMessages;
                });
            } else {
                const reader = response.body?.getReader();
                const decoder = new TextDecoder();
                let accumulated = '';
                let streamBuffer = '';
                if (!reader) return;

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    streamBuffer += decoder.decode(value, { stream: true });
                    const lines = streamBuffer.split('\n');
                    streamBuffer = lines.pop() || ''; // keep trailing incomplete line

                    for (const rawLine of lines) {
                        const line = rawLine.trim();
                        if (line.startsWith('data: ')) {
                            const payload = line.slice(6).trim();
                            if (payload === '[DONE]') continue;
                            try {
                                const data = JSON.parse(payload);
                                if (data.error) {
                                    accumulated += `\n\n⚠️ ${data.error}`;
                                    setMessages(prev => {
                                        const newMessages = [...prev];
                                        newMessages[newMessages.length - 1] = { role: 'assistant', content: accumulated.trim() };
                                        return newMessages;
                                    });
                                }
                                if (data.content) {
                                    accumulated += data.content;
                                    setMessages(prev => {
                                        const newMessages = [...prev];
                                        newMessages[newMessages.length - 1] = { role: 'assistant', content: accumulated };
                                        return newMessages;
                                    });
                                }
                                if (data.meta?.detected_scheme) setDetectedScheme(data.meta.detected_scheme);
                            } catch (e) { }
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Chat Error:', error);
            setMessages(prev => {
                const newMessages = [...prev];
                newMessages[newMessages.length - 1] = { 
                    role: 'assistant', 
                    content: '⚠️ Could not connect to Yojana-Setu server. Render backend may be waking up from sleep (~30s). Please try sending your message again in a moment.' 
                };
                return newMessages;
            });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex h-screen bg-white text-slate-800 overflow-hidden font-sans">
            {/* Tiranga Header */}
            <header className="fixed top-0 left-0 right-0 h-20 bg-white border-b-4 border-slate-100 flex items-center justify-between px-10 z-50 shadow-sm">
                <div className="flex items-center gap-4">
                    <Link href="/" className="text-slate-400 hover:text-blue-600 transition-colors">
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                        </svg>
                    </Link>
                    <div className="border-2 border-blue-100 px-4 py-1 rounded-xl bg-blue-50/20">
                        <h1 className="text-2xl font-black tracking-tighter">
                            <span className="text-[#FF9933]">Yojana</span>
                            <span className="text-slate-200">-</span>
                            <span className="text-[#138808]">Setu</span>
                        </h1>
                    </div>
                </div>
                <div className="flex gap-4">
                    <button onClick={() => setShowPortal(!showPortal)} className={`px-4 py-2 border-2 rounded-xl text-xs font-black transition-all ${showPortal ? 'bg-orange-50 border-[#FF9933] text-[#FF9933]' : 'bg-slate-50 border-slate-200 text-slate-400'}`}>
                        PORTAL VIEW
                    </button>
                    <Link href="/" className="px-4 py-2 bg-slate-50 border-2 border-slate-200 rounded-xl text-xs font-black text-slate-600 hover:bg-slate-100 transition-all">
                        HOME
                    </Link>
                </div>
            </header>

            <div className="flex w-full mt-20 relative">
                {/* Chat Panel */}
                <main className={`${showPortal ? 'w-[55%]' : 'w-full'} flex flex-col transition-all duration-500 bg-white`}>
                    <div className="flex-1 overflow-y-auto px-6 py-10 space-y-10 custom-scrollbar">
                        <div className="max-w-4xl mx-auto space-y-10 pb-32">
                            {messages.map((msg, idx) => (
                                <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-in fade-in slide-in-from-bottom-4 duration-500`}>
                                    <div className={`
                                        max-w-[85%] px-6 py-5 rounded-2xl relative
                                        ${msg.role === 'user'
                                            ? 'bg-white border-2 border-[#FF9933] text-slate-800 shadow-sm'
                                            : 'bg-white border-l-4 border-l-[#FF9933] border-r-4 border-r-[#138808] border-t border-b border-slate-100 shadow-lg shadow-slate-100'}
                                    `}>
                                        <div className={`text-[9px] font-black uppercase tracking-widest mb-2 ${msg.role === 'user' ? 'text-[#FF9933]' : 'text-orange-500'}`}>
                                            {msg.role === 'user' ? 'Citizen Request' : 'Yojna Setu Assistance'}
                                        </div>
                                        <div className="prose prose-sm max-w-none text-slate-700 font-medium">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                                        </div>
                                    </div>
                                </div>
                            ))}
                            {isLoading && (
                                <div className="flex justify-start">
                                    <div className="bg-slate-50 border border-slate-100 px-5 py-3 rounded-2xl flex gap-3 items-center">
                                        <div className="flex gap-1">
                                            <span className="w-1.5 h-1.5 bg-[#FF9933] rounded-full animate-bounce"></span>
                                            <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce delay-100"></span>
                                            <span className="w-1.5 h-1.5 bg-[#138808] rounded-full animate-bounce delay-200"></span>
                                        </div>
                                        <span className="text-[10px] font-black text-slate-400">PROCESSING...</span>
                                    </div>
                                </div>
                            )}
                            <div ref={messagesEndRef} />
                        </div>
                    </div>

                    {/* Floating Input Bar */}
                    <div className="fixed bottom-10 left-0 right-0 z-40 pointer-events-none">
                        <div className={`${showPortal ? 'w-[55%]' : 'w-full'} transition-all duration-500 px-6 pointer-events-auto`}>
                            <form onSubmit={handleSendMessage} className="max-w-4xl mx-auto bg-white border-2 border-slate-100 p-2 rounded-2xl shadow-2xl flex items-center gap-2">
                                <button type="button" onClick={() => fileInputRef.current?.click()} className="w-12 h-12 flex items-center justify-center rounded-xl bg-slate-50 text-slate-400 hover:text-orange-500 hover:bg-orange-50 transition-colors">
                                    <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                                    </svg>
                                </button>
                                <input type="file" ref={fileInputRef} className="hidden" multiple onChange={(e) => setSelectedFiles(prev => [...prev, ...Array.from(e.target.files || [])])} />

                                <input
                                    type="text"
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    placeholder="Puchhiye: PM Kisan eligibility kya hai?"
                                    className="flex-1 py-3 px-2 outline-none font-medium text-slate-700 placeholder-slate-300"
                                    disabled={isLoading}
                                />

                                <button type="button" onClick={isRecording ? stopRecording : startRecording} className={`w-12 h-12 flex items-center justify-center rounded-xl transition-all ${isRecording ? 'bg-red-500 text-white animate-pulse' : 'text-slate-400 hover:bg-slate-50 hover:text-blue-500'}`}>
                                    {isRecording ? (
                                        <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1 1 1 0 011 1v4a1 1 0 01-1 1 1 1 0 01-1-1v-4zM13 10a1 1 0 011-1 1 1 0 011 1v4a1 1 0 01-1 1 1 1 0 01-1-1v-4z" />
                                        </svg>
                                    ) : (
                                        <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                                        </svg>
                                    )}
                                </button>

                                <button
                                    type="submit"
                                    disabled={isLoading || (!input.trim() && selectedFiles.length === 0)}
                                    className="px-8 py-3 rounded-xl font-black text-xs uppercase tracking-widest transition-all disabled:bg-slate-200 disabled:text-slate-400 bg-[#138808] text-white hover:bg-[#0f6b06]"
                                >
                                    SEND
                                </button>
                            </form>

                            {selectedFiles.length > 0 && (
                                <div className="max-w-4xl mx-auto mt-2 flex flex-wrap gap-2 px-2">
                                    {selectedFiles.map((f, i) => (
                                        <div key={i} className="bg-blue-50 text-blue-600 px-3 py-1 rounded-lg text-[10px] font-bold border border-blue-100 flex items-center gap-2">
                                            <span>📎 {f.name}</span>
                                            <button type="button" onClick={() => setSelectedFiles(prev => prev.filter((_, idx) => idx !== i))} className="hover:text-red-500">×</button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </main>

                {/* Actual Website Sidebar */}
                {showPortal && (
                    <div className="w-[45%] h-[calc(100vh-80px)] border-l-4 border-slate-100 bg-slate-50 animate-in slide-in-from-right duration-500 overflow-hidden">
                        <div className="h-full w-full relative">
                            <iframe
                                ref={iframeRef}
                                src={portalUrl}
                                onLoad={handleIframeLoad}
                                className="w-full h-full border-none"
                                title="Government Portal"
                            />
                            <div className="absolute top-4 right-4 bg-[#003366] text-white px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest shadow-lg">
                                Live Official Portal
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
