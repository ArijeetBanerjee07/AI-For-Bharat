'use client';

import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

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

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        const phone = localStorage.getItem('user_phone');
        const name = localStorage.getItem('user_name');

        if (phone && name) {
            setUserPhone(phone);
            setUserName(name);
            setMessages([
                {
                    role: 'assistant',
                    content: `Namaste ${name}! Main Yojna Setu AI hoon. Main aapki sarkari yojanaon (government schemes) ke baare mein jaankari paane aur aavedan (apply) karne mein madad kar sakta hoon. Aap mujhse kisi bhi scheme ke baare mein pooch sakte hain.`
                }
            ]);
        } else {
            // If no registration, redirect back or use default
            setUserPhone('9876543210');
            setUserName('Guest User');
            setMessages([
                {
                    role: 'assistant',
                    content: 'Namaste! Kripya register karein ya chat shuru karein.'
                }
            ]);
        }
    }, []);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);


    const [isRecording, setIsRecording] = useState(false);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            audioChunksRef.current = [];

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunksRef.current.push(event.data);
                }
            };

            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
                handleVoiceMessage(audioBlob);
                stream.getTracks().forEach(track => track.stop());
            };

            mediaRecorder.start();
            setIsRecording(true);
        } catch (err) {
            console.error("Mic access denied:", err);
            alert("Kripya microphone access allow karein.");
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
        // Add a temporary "User is speaking..." message
        setMessages(prev => [...prev, { role: 'user', content: "🎙️ Processing voice..." }]);
        setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

        try {
            const formData = new FormData();
            formData.append('audio', audioBlob, 'voice.wav');
            formData.append('user_name', userName || "Citizen");
            if (detectedScheme) formData.append('scheme_id', detectedScheme);

            const response = await fetch('http://localhost:8000/api/voice-agent', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) throw new Error('Voice API failed');

            const data = await response.json();

            // Update messages with transcribed text and agent reply
            setMessages(prev => {
                const newMessages = [...prev];
                // Update user transcript
                newMessages[newMessages.length - 2] = {
                    role: 'user',
                    content: `🎙️ ${data.user_text}`
                };
                // Update assistant response
                newMessages[newMessages.length - 1] = {
                    role: 'assistant',
                    content: data.agent_text
                };
                return newMessages;
            });

            if (data.meta?.scheme) setDetectedScheme(data.meta.scheme);

            // Play the audio response
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
                    content: 'Kshama kijiye, awaaz samajhne mein dikkat hui.'
                };
                return newMessages;
            });
        } finally {
            setIsLoading(false);
        }
    };

    const handleSendMessage = async (e: React.FormEvent) => {
        e.preventDefault();
        if ((!input.trim() && selectedFiles.length === 0) || isLoading) return;

        const userMessage = input.trim();
        const filesToSend = [...selectedFiles];

        setInput('');
        setSelectedFiles([]);

        // Display message with files if exist
        let displayContent = userMessage;
        if (filesToSend.length > 0) {
            const fileList = filesToSend.map(f => `📎 *${f.name}*`).join('\n');
            displayContent += `\n\n${fileList}`;
        }

        setMessages(prev => [...prev, { role: 'user', content: displayContent }]);
        setIsLoading(true);

        // Add a placeholder for the assistant's stream
        setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

        try {
            const formData = new FormData();
            formData.append('user_text', userMessage || "Evaluating documents...");
            formData.append('user_name', userName || "Citizen");

            if (filesToSend.length > 0) {
                filesToSend.forEach(file => {
                    formData.append('documents', file);
                });
                // If we detected a scheme previously, send it
                if (detectedScheme) {
                    formData.append('scheme_id', detectedScheme);
                }
            }

            const response = await fetch('http://localhost:8000/api/agent', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) throw new Error('API request failed');

            const contentType = response.headers.get('content-type') || '';

            // ----- ROUTE A: JSON response (apply/clarify routes) -----
            if (contentType.includes('application/json')) {
                const data = await response.json();
                const responseText = data.response || data.agent_response || JSON.stringify(data);
                setMessages(prev => {
                    const newMessages = [...prev];
                    newMessages[newMessages.length - 1] = {
                        role: 'assistant',
                        content: responseText
                    };
                    return newMessages;
                });

                // ----- ROUTE B: SSE streaming response (query route) -----
            } else {
                if (!response.body) throw new Error('No response body');

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let accumulatedContent = '';

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n');

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const dataStr = line.slice(6).trim();
                            if (dataStr === '[DONE]') continue;

                            try {
                                const data = JSON.parse(dataStr);
                                if (data.content) {
                                    accumulatedContent += data.content;
                                    setMessages(prev => {
                                        const newMessages = [...prev];
                                        newMessages[newMessages.length - 1] = {
                                            role: 'assistant',
                                            content: accumulatedContent
                                        };
                                        return newMessages;
                                    });
                                }
                                if (data.meta && data.meta.detected_scheme) {
                                    setDetectedScheme(data.meta.detected_scheme);
                                }
                            } catch (e) {
                                console.error('Error parsing stream chunk:', e);
                            }
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
                    content: 'Maaf kijiye, server se judne mein dikkat ho rahi hai.'
                };
                return newMessages;
            });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-screen bg-white text-slate-800 overflow-hidden font-sans">
            {/* Indigenous Tiranga Header */}
            <header className="flex items-center justify-between px-6 py-4 bg-white border-b-4 border-slate-100 shrink-0 z-20 shadow-[0_4px_20px_-5px_rgba(255,153,51,0.2),0_4px_20px_-5px_rgba(19,136,8,0.2)]">
                <div className="flex items-center gap-4">
                    <Link href="/register" className="text-slate-400 hover:text-blue-600 transition-colors">
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                        </svg>
                    </Link>
                    <div className="border-2 border-blue-100 px-3 py-1 rounded-xl bg-blue-50/30 shadow-[0_0_15px_rgba(59,130,246,0.1)]">
                        <h1 className="text-2xl font-black tracking-tighter">
                            <span className="text-[#FF9933]">Yojana</span>
                            <span className="text-slate-200 transition-opacity">-</span>
                            <span className="text-[#138808]">Setu</span>
                        </h1>
                    </div>
                </div>

                <div className="flex gap-3">
                    <Link href="/" className="px-4 py-2 bg-slate-50 border-2 border-slate-200 rounded-xl text-xs font-black text-slate-600 hover:bg-slate-100 transition-all">
                        HOME
                    </Link>
                </div>
            </header>

            <div className="flex flex-1 overflow-hidden relative">
                {/* Chat Panel (Full width focus) */}
                <main className="flex-1 transition-all duration-700 flex flex-col bg-white">
                    <div className="flex-1 overflow-y-auto p-4 sm:p-8 space-y-8 no-scrollbar">
                        <div className="max-w-4xl mx-auto space-y-10">
                            {messages.map((msg, idx) => (
                                <div
                                    key={idx}
                                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-in fade-in slide-in-from-bottom-4 duration-700`}
                                >
                                    <div className={`
                                        max-w-[85%] sm:max-w-[75%] px-6 py-5 rounded-2xl transition-all
                                        ${msg.role === 'user'
                                            ? 'bg-orange-50 border-2 border-[#FF9933] text-orange-900 shadow-sm'
                                            : 'bg-white text-slate-800 border-l-4 border-l-[#FF9933] border-r-4 border-r-[#138808] border-t border-b border-slate-100 shadow-[0_10px_30px_-10px_rgba(255,153,51,0.2),0_10px_30px_-10px_rgba(19,136,8,0.2)]'}
                                    `}>
                                        <div className={`text-[10px] font-black uppercase tracking-widest mb-3 ${msg.role === 'user' ? 'text-orange-600' : 'text-[#FF9933]'}`}>
                                            {msg.role === 'user' ? 'Citizen Request' : 'Yojna Setu Assistance'}
                                        </div>
                                        <div className={`prose prose-sm max-w-none font-medium leading-[1.8] ${msg.role === 'user' ? 'prose-orange' : 'prose-slate'}`}>
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                {msg.content}
                                            </ReactMarkdown>
                                        </div>
                                    </div>
                                </div>
                            ))}
                            {isLoading && (
                                <div className="flex justify-start">
                                    <div className="bg-slate-50 border border-slate-200 px-5 py-4 rounded-2xl flex gap-3 items-center">
                                        <div className="flex gap-1.5">
                                            <span className="w-2 h-2 bg-[#FF9933] rounded-full animate-bounce"></span>
                                            <span className="w-2 h-2 bg-slate-300 rounded-full animate-bounce [animation-delay:0.2s]"></span>
                                            <span className="w-2 h-2 bg-[#138808] rounded-full animate-bounce [animation-delay:0.4s]"></span>
                                        </div>
                                        <span className="text-xs font-black text-slate-400 uppercase tracking-widest">Processing Scheme Data...</span>
                                    </div>
                                </div>
                            )}
                            <div ref={messagesEndRef} />
                        </div>
                    </div>

                    {/* Chat Input - Floating Indigenous Design */}
                    <div className="p-6 bg-white border-t border-slate-100">
                        <form onSubmit={handleSendMessage} className="max-w-4xl mx-auto flex flex-col gap-2">
                            {selectedFiles.length > 0 && (
                                <div className="flex flex-wrap gap-2 mb-2 animate-in slide-in-from-bottom-2">
                                    {selectedFiles.map((file, idx) => (
                                        <div key={idx} className="flex items-center gap-2 px-3 py-1.5 bg-orange-50 border border-orange-100 rounded-xl">
                                            <span className="text-[10px] font-bold text-orange-700 truncate max-w-[120px]">📎 {file.name}</span>
                                            <button
                                                type="button"
                                                onClick={() => setSelectedFiles(prev => prev.filter((_, i) => i !== idx))}
                                                className="text-orange-300 hover:text-orange-500 transition-colors"
                                            >
                                                <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                                </svg>
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                            <div className="flex gap-4">
                                <div className="flex-1 relative flex items-center">
                                    <button
                                        type="button"
                                        onClick={() => fileInputRef.current?.click()}
                                        className="absolute left-3 w-10 h-10 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-[#FF9933] hover:text-white transition-all z-10"
                                        title="Upload Document"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                                        </svg>
                                    </button>
                                    <input
                                        type="file"
                                        ref={fileInputRef}
                                        className="hidden"
                                        multiple
                                        onChange={(e) => {
                                            const files = Array.from(e.target.files || []);
                                            if (files.length > 0) {
                                                setSelectedFiles(prev => [...prev, ...files]);
                                            }
                                            e.target.value = '';
                                        }}
                                        accept=".pdf,image/*"
                                    />
                                    <input
                                        type="text"
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        placeholder="Puchhiye: PM Kisan eligibility kya hai?"
                                        className="w-full bg-slate-50 border-2 border-slate-100 rounded-2xl pl-16 pr-24 py-5 text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#FF9933] focus:bg-white transition-all font-semibold shadow-sm"
                                        disabled={isLoading}
                                    />
                                    <button
                                        type="button"
                                        onClick={isRecording ? stopRecording : startRecording}
                                        className={`absolute right-3 w-12 h-12 flex items-center justify-center rounded-xl transition-all z-10 ${isRecording ? 'bg-red-500 text-white animate-pulse' : 'bg-blue-50 text-blue-600 hover:bg-blue-600 hover:text-white'}`}
                                        title={isRecording ? "Stop Recording" : "Start Voice Chat"}
                                    >
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
                                </div>
                                <button
                                    type="submit"
                                    disabled={(!input.trim() && selectedFiles.length === 0) || isLoading}
                                    className="bg-[#138808] hover:bg-[#0f6c06] disabled:bg-slate-200 disabled:text-slate-400 text-white px-8 rounded-2xl transition-all shadow-lg active:scale-95 flex items-center justify-center border-b-4 border-[#0a4d04]"
                                >
                                    <span className="font-black">SEND</span>
                                </button>
                            </div>
                        </form>
                        <p className="text-center text-[10px] text-slate-400 mt-4 font-bold uppercase tracking-widest">Digital India • Yojana-Setu AI Powered</p>
                    </div>
                </main>
            </div>
        </div>
    );
}
