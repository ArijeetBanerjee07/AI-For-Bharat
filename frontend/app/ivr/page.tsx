'use client';

import { useRouter } from 'next/navigation';
import { API_BASE_URL } from '@/lib/constants';
import React, { useEffect, useState, useRef } from 'react';
import Link from 'next/link';

export default function BrowserIVR() {
    const [callState, setCallState] = useState<'dialing' | 'connected' | 'listening' | 'processing' | 'speaking' | 'ended'>('dialing');
    const [timer, setTimer] = useState(0);
    const [transcript, setTranscript] = useState('');
    const [aiText, setAiText] = useState('');

    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);
    const audioControlRef = useRef<HTMLAudioElement | null>(null);
    const streamRef = useRef<MediaStream | null>(null);

    const sayGreeting = async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/voice-agent/welcome`);
            if (!res.ok) throw new Error("Failed to fetch welcome audio");
            const data = await res.json();

            if (data.audio_base64) {
                const audioUrl = `data:audio/wav;base64,${data.audio_base64}`;
                const audio = new Audio(audioUrl);
                audioControlRef.current = audio;

                audio.onplay = () => setCallState('speaking');
                audio.onended = () => setCallState('connected');

                try {
                    await audio.play();
                } catch (playErr) {
                    console.log("Autoplay policy deferred audio, set state connected", playErr);
                    setCallState('connected');
                }
            } else {
                setCallState('connected');
            }
        } catch (err) {
            console.error("Welcome greeting error:", err);
            setCallState('connected');
        }
    };

    useEffect(() => {
        if (callState === 'dialing') {
            const t = setTimeout(() => {
                setCallState('connected');
                sayGreeting();
            }, 1500); // 1.5 second ringing
            return () => clearTimeout(t);
        }
    }, [callState]);

    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (['connected', 'listening', 'processing', 'speaking'].includes(callState)) {
            interval = setInterval(() => setTimer(prev => prev + 1), 1000);
        }
        return () => clearInterval(interval);
    }, [callState]);

    const formatTime = (secs: number) => {
        const m = Math.floor(secs / 60).toString().padStart(2, '0');
        const s = (secs % 60).toString().padStart(2, '0');
        return `${m}:${s}`;
    };

    const toggleRecording = async () => {
        if (callState === 'listening') {
            // Stop recording
            if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
                mediaRecorderRef.current.stop();
            }
            return;
        }

        // Start recording
        if (window.speechSynthesis.speaking) {
            window.speechSynthesis.cancel();
        }
        if (audioControlRef.current) {
            audioControlRef.current.pause();
            audioControlRef.current.currentTime = 0;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            streamRef.current = stream;
            audioChunksRef.current = [];

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) {
                    audioChunksRef.current.push(e.data);
                }
            };

            mediaRecorder.onstop = async () => {
                stream.getTracks().forEach(track => track.stop());
                setCallState('processing');

                const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
                await sendAudioToAgent(audioBlob);
            };

            mediaRecorder.start();
            setCallState('listening');
            setTranscript('');
            setAiText('');
        } catch (err) {
            console.error("Mic error:", err);
            alert("Microphone access denied or error occurred.");
        }
    };

    const sendAudioToAgent = async (audioBlob: Blob) => {
        const formData = new FormData();
        const user_name = localStorage.getItem('user_name') || 'Citizen';

        // Convert Blob to File with proper webm extension
        const audioFile = new File([audioBlob], 'voice_query.webm', { type: 'audio/webm' });
        formData.append('audio', audioFile);
        formData.append('user_name', user_name);

        try {
            const res = await fetch(`${API_BASE_URL}/api/voice-agent`, {
                method: 'POST',
                body: formData
            });

            if (!res.ok) throw new Error("Agent API failed");

            const data = await res.json();
            setTranscript(data.user_text || "Unrecognized audio");
            setAiText(data.agent_text || "No response generated");

            if (data.audio_base64) {
                const audioUrl = `data:audio/wav;base64,${data.audio_base64}`;
                const audio = new Audio(audioUrl);
                audioControlRef.current = audio;

                audio.onplay = () => setCallState('speaking');
                audio.onended = () => setCallState('connected');

                try {
                    await audio.play();
                } catch (pErr) {
                    console.log("Audio play deferred by browser", pErr);
                    setCallState('connected');
                }
            } else {
                setCallState('connected');
            }

        } catch (err) {
            console.error(err);
            setAiText("Connection error. Try again.");
            setCallState('connected');
        }
    };

    const endCall = () => {
        if (window.speechSynthesis.speaking) window.speechSynthesis.cancel();
        if (audioControlRef.current) audioControlRef.current.pause();
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
            mediaRecorderRef.current.stop();
        }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
            streamRef.current = null;
        }
        setCallState('ended');
        setTimer(0);
    };

    if (callState === 'ended') {
        return (
            <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center p-8 text-center text-white font-sans">
                <h2 className="text-3xl font-black mb-4">Call Ended</h2>
                <p className="text-slate-400 mb-8">Thank you for using Yojana-Setu Voice Service.</p>
                <Link href="/" className="px-8 py-3 bg-[#FF9933]/20 hover:bg-[#FF9933]/30 text-[#FF9933] font-bold rounded-full transition-all border border-[#FF9933]/50">
                    Return to Dashboard
                </Link>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gradient-to-br transition-all duration-1000 from-slate-900 to-slate-800 flex flex-col justify-between items-center py-12 px-6 font-sans relative overflow-hidden">

            {/* Background Ambience Effects */}
            {callState === 'listening' && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20">
                    <div className="w-96 h-96 bg-[#138808] rounded-full blur-[100px] animate-pulse"></div>
                </div>
            )}
            {callState === 'speaking' && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20">
                    <div className="w-96 h-96 bg-[#FF9933] rounded-full blur-[100px] animate-pulse"></div>
                </div>
            )}

            {/* Header Info */}
            <div className="text-center z-10 w-full mt-8">
                <h1 className="text-white text-4xl font-black tracking-tight mb-2">Shubh</h1>
                <p className="text-slate-400 font-bold uppercase tracking-widest text-xs">Yojana-Setu AI Caseworker</p>
                <div className="text-[#FF9933] font-semibold tracking-widest mt-4 animate-pulse">
                    {callState === 'dialing' ? 'Dialing...'
                        : callState === 'listening' ? 'Listening...'
                            : callState === 'processing' ? 'Processing...'
                                : formatTime(timer)}
                </div>
            </div>

            {/* Animated Avatar Centerpiece */}
            <div className="relative flex items-center justify-center my-auto z-10">

                {/* Ringing/Active Ripples */}
                {(callState === 'dialing' || callState === 'speaking') && (
                    <>
                        <div className={`absolute w-48 h-48 rounded-full border border-${callState === 'speaking' ? '[#FF9933]' : 'white'} opacity-40 animate-ping`}></div>
                        <div className={`absolute w-64 h-64 rounded-full border border-${callState === 'speaking' ? '[#FF9933]' : 'white'} opacity-20 animate-[ping_2s_infinite]`}></div>
                    </>
                )}

                <div className={`w-36 h-36 rounded-full flex items-center justify-center shadow-2xl relative overflow-hidden transition-all duration-500 ${callState === 'speaking' ? 'bg-[#FF9933]/20 border-4 border-[#FF9933]'
                    : callState === 'listening' ? 'bg-[#138808]/20 border-4 border-[#138808] scale-110'
                        : 'bg-white/10 border-4 border-slate-700'
                    }`}>
                    {callState === 'speaking' ? (
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-16 w-16 text-[#FF9933]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072M17.95 6.05a8 8 0 010 11.9M6.05 17.95a8 8 0 010-11.9M8.464 15.536a5 5 0 010-7.072M12 12h.01" />
                        </svg>
                    ) : callState === 'listening' ? (
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-16 w-16 text-[#138808] animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                        </svg>
                    ) : (
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-16 w-16 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                    )}
                </div>
            </div>

            {/* Transcripts (for visual feedback) */}
            {(transcript || aiText) && (
                <div className="z-10 w-full max-w-sm px-6 mb-12 flex flex-col gap-4 text-center">
                    {transcript && <p className="text-slate-400 text-sm italic">"{transcript}"</p>}
                    {aiText && <p className="text-white font-medium">"{aiText}"</p>}
                </div>
            )}

            {/* Controls Container */}
            <div className="z-10 w-full max-w-md bg-white/5 backdrop-blur-xl border border-white/10 rounded-full py-6 flex justify-around items-center px-8 shadow-2xl">

                {/* Keypad */}
                <button className="flex flex-col items-center gap-2 group pointer-events-none opacity-50">
                    <div className="w-14 h-14 rounded-full bg-white/5 flex items-center justify-center border border-white/10">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                        </svg>
                    </div>
                    <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">Keypad</span>
                </button>

                {/* Speak Button (Center, Large) */}
                {!['dialing', 'processing'].includes(callState) && (
                    <div className="flex flex-col items-center relative -mt-10">
                        <button
                            onClick={toggleRecording}
                            className={`w-20 h-20 rounded-full flex items-center justify-center shadow-[0_0_30px_rgba(255,255,255,0.1)] transition-all ${callState === 'listening' ? 'bg-[#f43f5e] scale-110 shadow-[0_0_40px_rgba(244,63,94,0.5)] animate-pulse' : 'bg-[#138808] hover:bg-[#138808]/80 border-2 border-[#138808]/50'
                                }`}
                        >
                            {callState === 'listening' ? (
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
                                </svg>
                            ) : (
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                                </svg>
                            )}
                        </button>
                        <span className="text-[10px] uppercase tracking-widest text-[#f8fafc] font-black mt-4 whitespace-nowrap">
                            {callState === 'listening' ? 'Press to Send' : 'Press to Talk'}
                        </span>
                    </div>
                )}

                {/* End Call */}
                <button onClick={endCall} className="flex flex-col items-center gap-2 group">
                    <div className="w-14 h-14 rounded-full bg-red-500/20 hover:bg-red-500 flex items-center justify-center transition-colors border border-red-500/50">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-red-500 group-hover:text-white transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 8l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2M5 3a2 2 0 00-2 2v1c0 8.284 6.716 15 15 15h1a2 2 0 002-2v-3.28a1 1 0 00-.684-.948l-4.493-1.498a1 1 0 00-1.21.502l-1.13 2.257a11.042 11.042 0 01-5.516-5.516l1.13-2.257a1 1 0 00-.502-1.21l-4.493-1.498A1 1 0 005 4.72V3z" />
                        </svg>
                    </div>
                    <span className="text-[10px] uppercase tracking-widest text-red-400 font-bold group-hover:text-red-500 transition-colors">End</span>
                </button>

            </div>
        </div>
    );
}
