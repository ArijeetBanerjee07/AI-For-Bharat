'use client';

import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '@/lib/constants';
import Link from 'next/link';

export default function DebugPage() {
    const [phone, setPhone] = useState('');
    const [debugData, setDebugData] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        const storedPhone = localStorage.getItem('user_phone');
        if (storedPhone) {
            setPhone(storedPhone);
        }
    }, []);

    const handleCheckStorage = async () => {
        if (!phone) {
            setError('Please enter a phone number');
            return;
        }

        setLoading(true);
        setError('');

        try {
            const response = await fetch(`${API_BASE_URL}/api/debug/storage/${phone}`);
            const data = await response.json();
            setDebugData(data);
            console.log('Debug data:', data);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-white p-8">
            <div className="max-w-4xl mx-auto">
                <Link href="/" className="text-blue-600 hover:underline mb-4 block">&larr; Back to Dashboard</Link>
                
                <h1 className="text-3xl font-bold mb-8">Debug Storage</h1>

                <div className="bg-gray-50 p-6 rounded-lg mb-8">
                    <div className="mb-4">
                        <label className="block text-sm font-medium mb-2">Phone Number:</label>
                        <input
                            type="text"
                            value={phone}
                            onChange={(e) => setPhone(e.target.value)}
                            placeholder="Enter phone number (from localStorage)"
                            className="w-full px-4 py-2 border rounded-lg"
                        />
                    </div>

                    <button
                        onClick={handleCheckStorage}
                        disabled={loading}
                        className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
                    >
                        {loading ? 'Checking...' : 'Check Storage Status'}
                    </button>

                    {error && <p className="text-red-600 mt-4">Error: {error}</p>}
                </div>

                {debugData && (
                    <div className="bg-gray-50 p-6 rounded-lg">
                        <h2 className="text-xl font-bold mb-4">Storage Status</h2>
                        
                        <div className="mb-6">
                            <h3 className="font-bold mb-2">Summary:</h3>
                            <ul className="text-sm space-y-1">
                                <li>User ID: <code className="bg-gray-200 px-2 py-1">{debugData.user_id}</code></li>
                                <li>DynamoDB Available: <strong>{debugData.dynamodb_available ? '✅ Yes' : '❌ No (using memory fallback)'}</strong></li>
                                <li>Memory Sessions: {debugData.memory_sessions_count}</li>
                                <li>Memory Messages: {debugData.memory_messages_count}</li>
                                <li>Sessions for this user: {debugData.user_sessions?.length || 0}</li>
                            </ul>
                        </div>

                        <div className="mb-6">
                            <h3 className="font-bold mb-2">Sessions for this User:</h3>
                            {debugData.user_sessions && debugData.user_sessions.length > 0 ? (
                                <pre className="bg-gray-100 p-4 rounded text-xs overflow-auto max-h-96">
                                    {JSON.stringify(debugData.user_sessions, null, 2)}
                                </pre>
                            ) : (
                                <p className="text-gray-500">No sessions found</p>
                            )}
                        </div>

                        <div className="mb-6">
                            <h3 className="font-bold mb-2">All Memory Sessions:</h3>
                            {debugData.all_memory_sessions && debugData.all_memory_sessions.length > 0 ? (
                                <div className="bg-gray-100 p-4 rounded">
                                    {debugData.all_memory_sessions.map((session: any, idx: number) => (
                                        <div key={idx} className="mb-2 text-xs border-b pb-2">
                                            <div><strong>Session ID:</strong> {session.session_id}</div>
                                            <div><strong>User ID:</strong> {session.user_id}</div>
                                            <div><strong>Title:</strong> {session.title}</div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <p className="text-gray-500">No sessions in memory</p>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
