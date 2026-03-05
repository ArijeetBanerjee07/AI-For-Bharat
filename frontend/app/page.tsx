'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

interface Application {
  id: string;
  scheme: string;
  status: string;
  date: string;
  beneficiary: string;
}

export default function Dashboard() {
  const [userName, setUserName] = useState<string | null>(null);
  const [userPhone, setUserPhone] = useState<string | null>(null);
  const router = useRouter();

  // Empty applications state
  const [applications] = useState<Application[]>([]);

  useEffect(() => {
    const name = localStorage.getItem('user_name');
    const phone = localStorage.getItem('user_phone');
    if (name && phone) {
      setUserName(name);
      setUserPhone(phone);
    } else {
      // Force redirect to login if not authenticated
      router.push('/login');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSignOut = () => {
    localStorage.removeItem('user_name');
    localStorage.removeItem('user_phone');
    router.push('/login');
  };

  return (
    <div className="min-h-screen bg-white text-slate-800 font-sans">
      {/* Indigenous Navbar */}
      <nav className="flex items-center justify-between px-8 py-4 bg-white border-b-4 border-slate-50 sticky top-0 z-50 shadow-[0_4px_20px_-5px_rgba(255,153,51,0.1),0_4px_20px_-5px_rgba(19,136,8,0.1)]">
        <div className="flex items-center gap-6">
          <div className="border-2 border-blue-100 px-4 py-1.5 rounded-2xl bg-blue-50/30 shadow-[0_0_15px_rgba(59,130,246,0.1)]">
            <h1 className="text-2xl font-black tracking-tighter">
              <span className="text-[#FF9933]">Yojana</span>
              <span className="text-slate-200">-</span>
              <span className="text-[#138808]">Setu</span>
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="hidden md:flex flex-col items-end">
            <span className="text-[10px] font-black uppercase tracking-widest text-[#FF9933]">Active Citizen</span>
            <span className="text-sm font-bold text-slate-700">{userName || 'Loading...'}</span>
          </div>
          <button
            onClick={handleSignOut}
            className="px-6 py-2 border-2 border-[#138808] text-[#138808] rounded-xl font-black text-xs hover:bg-[#138808] hover:text-white transition-all active:scale-95 uppercase tracking-widest"
          >
            Sign Out
          </button>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto p-8 space-y-12">
        {/* Welcome Section */}
        <div className="space-y-2">
          <h2 className="text-3xl font-black tracking-tight text-slate-900">Namaste, {userName?.split(' ')[0]}!</h2>
          <p className="text-slate-500 font-medium">Welcome to your Indian Citizen Dashboard. Access your schemes and check application status.</p>
        </div>

        {/* Main Action Cards - Horizontal Layout */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <Link href="/chat" className="group">
            <div className="relative h-48 bg-white rounded-[2rem] p-8 overflow-hidden transition-all duration-500 border-2 border-slate-100 shadow-[0_15px_40px_-5px_rgba(255,153,51,0.2),0_15px_40px_-5px_rgba(19,136,8,0.2)] hover:-translate-y-2 hover:border-[#FF9933]/30">
              <div className="relative h-full flex flex-col justify-center">
                <div className="flex items-center gap-4 mb-4">
                  <div className="w-14 h-14 bg-slate-50 border-2 border-[#FF9933]/15 rounded-2xl flex items-center justify-center shadow-sm">
                    <div className="flex flex-col gap-1 w-6">
                      <div className="h-1 w-full bg-[#FF9933] rounded-full"></div>
                      <div className="h-1 w-full bg-slate-200 rounded-full"></div>
                      <div className="h-1 w-full bg-[#138808] rounded-full"></div>
                    </div>
                  </div>
                  <h3 className="text-3xl font-black tracking-tighter text-slate-800">Apka Sathi</h3>
                </div>
                <p className="text-slate-500 font-bold text-sm max-w-sm">Agent chat section for queries. Proactively find eligibility and apply to schemes.</p>
              </div>
            </div>
          </Link>

          <Link href="/ivr" className="group">
            <div className="relative h-48 bg-white rounded-[2rem] p-8 overflow-hidden transition-all duration-500 border-2 border-slate-100 shadow-[0_15px_40px_-5px_rgba(255,153,51,0.2),0_15px_40px_-5px_rgba(19,136,8,0.2)] hover:-translate-y-2 hover:border-[#138808]/30">
              <div className="relative h-full flex flex-col justify-center">
                <div className="flex items-center gap-4 mb-4">
                  <div className="w-14 h-14 bg-slate-50 border-2 border-[#138808]/15 rounded-2xl flex items-center justify-center shadow-sm">
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-7 h-7 text-[#138808]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                    </svg>
                  </div>
                  <h3 className="text-2xl font-black tracking-tight leading-tight text-slate-800">Call karke <br />sahayata payiye</h3>
                </div>
                <p className="text-slate-500 font-medium text-sm max-w-xs">Talk directly to our AI caseworker in your local language for instant help.</p>
              </div>
            </div>
          </Link>
        </div>

        {/* Applications Section */}
        <div className="space-y-6 pt-4">
          <div className="flex items-center justify-between border-b pb-4">
            <h3 className="text-xl font-black uppercase tracking-widest text-slate-400">Your AI Applications</h3>
            <span className="px-3 py-1 bg-slate-100 rounded-full text-[10px] font-black text-slate-500">REAL-TIME STATUS</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <div className="col-span-full py-12 flex flex-col items-center justify-center border-2 border-dashed border-slate-100 rounded-[2rem] bg-slate-50/30">
              <p className="text-slate-400 font-bold text-sm tracking-tight text-center px-4">
                Abhi tak koi application nahi hai. 🇮🇳<br />
                <span className="text-xs font-medium opacity-70">No active applications found. Access 'Apka Sathi' to apply.</span>
              </p>
            </div>
          </div>
        </div>
      </main>

      {/* Cultural Footer */}
      <footer className="mt-20 border-t border-slate-100 p-12 bg-slate-50/50">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-8">
          <div className="text-center md:text-left">
            <p className="text-[10px] font-black text-[#FF9933] uppercase tracking-[0.3em] mb-2">Developed by Indian Engineers</p>
            <p className="text-slate-400 text-xs font-medium max-w-xs">Building a digital bridge for every citizen to access their government benefits with AI.</p>
          </div>
          <div className="flex h-1.5 w-64 rounded-full overflow-hidden shadow-sm">
            <div className="flex-1 bg-[#FF9933]"></div>
            <div className="flex-1 bg-white"></div>
            <div className="flex-1 bg-[#138808]"></div>
          </div>
        </div>
      </footer>
    </div>
  );
}
