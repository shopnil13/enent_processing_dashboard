import React, { useState } from 'react';
import { submitEvents, ItemResult } from '../api';

interface JsonSubmitFormProps {
  onSuccess: () => void;
}

export const JsonSubmitForm: React.FC<JsonSubmitFormProps> = ({ onSuccess }) => {
  const [jsonText, setJsonText] = useState<string>(
    JSON.stringify(
      {
        source_id: 'line_1',
        event_id: `evt_${Date.now()}`,
        type: 'COUNT',
        quantity: 15,
        event_time: new Date().toISOString(),
      },
      null,
      2
    )
  );
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [results, setResults] = useState<ItemResult[] | null>(null);

  const handleTemplate = (type: 'COUNT' | 'VOID' | 'BATCH') => {
    setLocalError(null);
    setResults(null);
    const now = new Date().toISOString();
    if (type === 'COUNT') {
      setJsonText(
        JSON.stringify(
          {
            source_id: 'line_1',
            event_id: `evt_c_${Date.now()}`,
            type: 'COUNT',
            quantity: 25,
            event_time: now,
          },
          null,
          2
        )
      );
    } else if (type === 'VOID') {
      setJsonText(
        JSON.stringify(
          {
            source_id: 'line_1',
            event_id: `evt_v_${Date.now()}`,
            type: 'VOID',
            target_event_id: 'evt_c_123',
            event_time: now,
          },
          null,
          2
        )
      );
    } else {
      setJsonText(
        JSON.stringify(
          [
            {
              source_id: 'line_1',
              event_id: `batch_c_${Date.now()}_1`,
              type: 'COUNT',
              quantity: 10,
              event_time: now,
            },
            {
              source_id: 'line_1',
              event_id: `batch_c_${Date.now()}_2`,
              type: 'COUNT',
              quantity: 20,
              event_time: now,
            },
          ],
          null,
          2
        )
      );
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    setResults(null);

    let parsed: any;
    try {
      parsed = JSON.parse(jsonText);
    } catch (err: any) {
      setLocalError(`Invalid JSON syntax: ${err.message}`);
      return;
    }

    if (!parsed || (typeof parsed !== 'object')) {
      setLocalError('Payload must be a JSON object or array of objects');
      return;
    }

    try {
      setSubmitting(true);
      const res = await submitEvents(parsed);
      setResults(res);
      onSuccess();
    } catch (err: any) {
      setLocalError(err.message || 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'ACCEPTED':
        return <span className="badge badge-accepted">ACCEPTED</span>;
      case 'DUPLICATE':
        return <span className="badge badge-duplicate">DUPLICATE</span>;
      case 'PENDING_REFERENCE':
        return <span className="badge badge-pending">PENDING_REF</span>;
      case 'CONFLICT':
        return <span className="badge badge-conflict">CONFLICT</span>;
      case 'REJECTED':
      default:
        return <span className="badge badge-rejected">{status}</span>;
    }
  };

  return (
    <div className="card bg-white p-5 rounded-lg shadow-sm mb-6">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h2 className="text-lg font-bold text-gray-800">Event Ingestion (POST /api/events)</h2>
        <div className="flex gap-2 text-xs">
          <button type="button" onClick={() => handleTemplate('COUNT')} className="btn-secondary">
            + Sample COUNT
          </button>
          <button type="button" onClick={() => handleTemplate('VOID')} className="btn-secondary">
            + Sample VOID
          </button>
          <button type="button" onClick={() => handleTemplate('BATCH')} className="btn-secondary">
            + Sample Batch
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <textarea
          rows={6}
          value={jsonText}
          onChange={(e) => setJsonText(e.target.value)}
          className="w-full font-mono text-sm p-3 border border-gray-300 rounded-md bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Paste single JSON event object or array of event objects..."
          required
        />

        {localError && (
          <div className="mt-2 p-2 bg-red-50 border border-red-200 text-red-700 text-xs rounded">
            {localError}
          </div>
        )}

        <div className="mt-3 flex justify-end">
          <button
            type="submit"
            disabled={submitting}
            className="btn-primary"
          >
            {submitting ? 'Submitting...' : 'Send Event(s)'}
          </button>
        </div>
      </form>

      {results && results.length > 0 && (
        <div className="mt-4 pt-3 border-t border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Ingestion Results ({results.length}):</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="border-b bg-gray-50 text-left text-gray-500">
                  <th className="py-1 px-2">Status</th>
                  <th className="py-1 px-2">Event ID</th>
                  <th className="py-1 px-2">Source ID</th>
                  <th className="py-1 px-2">Reason / Details</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} className="border-b hover:bg-gray-50">
                    <td className="py-1 px-2">{getStatusBadge(r.status)}</td>
                    <td className="py-1 px-2 font-mono">{r.event_id || '-'}</td>
                    <td className="py-1 px-2">{r.source_id || '-'}</td>
                    <td className="py-1 px-2 text-gray-600">{r.reason || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
