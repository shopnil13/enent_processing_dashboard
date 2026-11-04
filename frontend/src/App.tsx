import React, { useState, useEffect, useCallback } from 'react';
import {
  fetchSummary,
  fetchPending,
  fetchExceptions,
  fetchSources,
  fetchMqttStatus,
  SummaryState,
  PendingEvent,
  SystemException,
  MqttStatus,
} from './api';
import { SummaryCards } from './components/SummaryCards';
import { JsonSubmitForm } from './components/JsonSubmitForm';
import { StateTable } from './components/StateTable';
import { MqttPanel } from './components/MqttPanel';
import './App.css';

export const App: React.FC = () => {
  const [selectedSource, setSelectedSource] = useState<string>('');
  const [sources, setSources] = useState<string[]>([]);
  const [summary, setSummary] = useState<SummaryState | null>(null);
  const [pendingEvents, setPendingEvents] = useState<PendingEvent[]>([]);
  const [exceptions, setExceptions] = useState<SystemException[]>([]);
  const [mqttStatus, setMqttStatus] = useState<MqttStatus | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setErrorMessage(null);
      const [sum, pend, exc, srcList, mqtt] = await Promise.all([
        fetchSummary(selectedSource || undefined),
        fetchPending(selectedSource || undefined),
        fetchExceptions(selectedSource || undefined),
        fetchSources(),
        fetchMqttStatus().catch(() => null),
      ]);

      setSummary(sum);
      setPendingEvents(pend);
      setExceptions(exc);
      setSources(srcList);
      if (mqtt) setMqttStatus(mqtt);
      setLastRefreshed(new Date());
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to refresh dashboard');
    } finally {
      setLoading(false);
    }
  }, [selectedSource]);

  useEffect(() => {
    loadData();
    // 5-second automatic polling
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [loadData]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 pb-12">
      {/* Top Navbar */}
      <header className="bg-slate-900 text-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-blue-600 flex items-center justify-center font-bold text-white text-lg shadow">
              N
            </div>
            <div>
              <h1 className="text-base font-bold tracking-tight">NorthBridge Production Counter</h1>
              <div className="text-[10px] text-slate-400 font-mono">FSE 01 - Modular Monolith Dashboard</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Source Filter */}
            <div className="flex items-center gap-2">
              <label htmlFor="source-filter" className="text-xs text-slate-300">
                Source:
              </label>
              <select
                id="source-filter"
                value={selectedSource}
                onChange={(e) => setSelectedSource(e.target.value)}
                className="bg-slate-800 text-white text-xs py-1.5 px-3 rounded border border-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="">All Sources (Global)</option>
                {sources.map((src) => (
                  <option key={src} value={src}>
                    {src}
                  </option>
                ))}
              </select>
            </div>

            {/* Refresh Button */}
            <button
              onClick={loadData}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs px-3 py-1.5 rounded font-medium transition flex items-center gap-1.5"
            >
              <span>{loading ? '↻ Refreshing...' : '↻ Refresh'}</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        {errorMessage && (
          <div className="mb-4 p-3 bg-red-100 border border-red-300 text-red-800 text-sm rounded-lg flex items-center justify-between">
            <span>{errorMessage}</span>
            <button onClick={() => setErrorMessage(null)} className="text-red-500 font-bold hover:text-red-700">
              ✕
            </button>
          </div>
        )}

        {/* MQTT Status Panel */}
        <MqttPanel status={mqttStatus} loading={loading} />

        {/* Summary Indicators */}
        <SummaryCards summary={summary} loading={loading} />

        {/* 2-Column Responsive Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-5">
            <JsonSubmitForm onSuccess={loadData} />
          </div>
          <div className="lg:col-span-7">
            <StateTable
              pendingEvents={pendingEvents}
              exceptions={exceptions}
              loading={loading}
              onRefresh={loadData}
            />
          </div>
        </div>

        <footer className="mt-8 text-center text-xs text-slate-400">
          Last updated: {lastRefreshed.toLocaleTimeString()} | Auto-refreshing every 5 seconds
        </footer>
      </main>
    </div>
  );
};

export default App;
