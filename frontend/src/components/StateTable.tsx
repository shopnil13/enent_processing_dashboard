import React, { useState } from 'react';
import { PendingEvent, SystemException, acknowledgeEvents } from '../api';

interface StateTableProps {
  pendingEvents: PendingEvent[];
  exceptions: SystemException[];
  loading: boolean;
  onRefresh: () => void;
}

export const StateTable: React.FC<StateTableProps> = ({
  pendingEvents,
  exceptions,
  loading,
  onRefresh,
}) => {
  const [activeTab, setActiveTab] = useState<'pending' | 'exceptions'>('pending');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [acking, setAcking] = useState<boolean>(false);
  const [ackFeedback, setAckFeedback] = useState<string | null>(null);

  const toggleSelectAll = () => {
    if (selectedIds.size === pendingEvents.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(pendingEvents.map((e) => e.event_id)));
    }
  };

  const toggleSelectOne = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedIds(next);
  };

  const handleAcknowledge = async () => {
    if (selectedIds.size === 0) return;
    setAcking(true);
    setAckFeedback(null);
    try {
      const results = await acknowledgeEvents(Array.from(selectedIds));
      const ackedCount = results.filter((r) => r.status === 'ACKED').length;
      setAckFeedback(`Successfully acknowledged ${ackedCount} event(s).`);
      setSelectedIds(new Set());
      onRefresh();
    } catch (err: any) {
      setAckFeedback(`Error acknowledging: ${err.message}`);
    } finally {
      setAcking(false);
    }
  };

  return (
    <div className="card bg-white p-5 rounded-lg shadow-sm mb-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex border-b border-gray-200">
          <button
            onClick={() => setActiveTab('pending')}
            className={`py-2 px-4 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === 'pending'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Pending Acknowledgment ({pendingEvents.length})
          </button>
          <button
            onClick={() => setActiveTab('exceptions')}
            className={`py-2 px-4 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === 'exceptions'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Exceptions & Errors ({exceptions.length})
          </button>
        </div>

        {activeTab === 'pending' && pendingEvents.length > 0 && (
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500">
              {selectedIds.size} of {pendingEvents.length} selected
            </span>
            <button
              onClick={handleAcknowledge}
              disabled={selectedIds.size === 0 || acking}
              className="btn-primary text-xs"
            >
              {acking ? 'Acknowledging...' : `Acknowledge Selected (${selectedIds.size})`}
            </button>
          </div>
        )}
      </div>

      {ackFeedback && (
        <div className="mb-3 p-2 bg-blue-50 border border-blue-200 text-blue-800 text-xs rounded">
          {ackFeedback}
        </div>
      )}

      {loading && (
        <div className="text-center py-6 text-gray-400 text-sm">Refreshing state data...</div>
      )}

      {!loading && activeTab === 'pending' && (
        <div className="overflow-x-auto">
          {pendingEvents.length === 0 ? (
            <div className="text-center py-8 text-gray-400 text-sm">
              No pending events to acknowledge. All processed counts are up to date!
            </div>
          ) : (
            <table className="min-w-full text-xs">
              <thead>
                <tr className="border-b bg-gray-50 text-left text-gray-500">
                  <th className="py-2 px-3 w-8">
                    <input
                      type="checkbox"
                      checked={selectedIds.size === pendingEvents.length && pendingEvents.length > 0}
                      onChange={toggleSelectAll}
                    />
                  </th>
                  <th className="py-2 px-3">Event ID</th>
                  <th className="py-2 px-3">Source</th>
                  <th className="py-2 px-3">Type</th>
                  <th className="py-2 px-3">Quantity</th>
                  <th className="py-2 px-3">Event Time</th>
                  <th className="py-2 px-3">Received At</th>
                </tr>
              </thead>
              <tbody>
                {pendingEvents.map((evt) => (
                  <tr key={evt.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 px-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(evt.event_id)}
                        onChange={() => toggleSelectOne(evt.event_id)}
                      />
                    </td>
                    <td className="py-2 px-3 font-mono font-medium text-gray-900">{evt.event_id}</td>
                    <td className="py-2 px-3">{evt.source_id}</td>
                    <td className="py-2 px-3">
                      <span className="badge badge-accepted">{evt.type}</span>
                    </td>
                    <td className="py-2 px-3 font-semibold text-gray-800">
                      {evt.quantity !== null ? evt.quantity : '-'}
                    </td>
                    <td className="py-2 px-3 text-gray-500">{new Date(evt.event_time).toLocaleString()}</td>
                    <td className="py-2 px-3 text-gray-500">{new Date(evt.received_at).toLocaleTimeString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {!loading && activeTab === 'exceptions' && (
        <div className="overflow-x-auto">
          {exceptions.length === 0 ? (
            <div className="text-center py-8 text-gray-400 text-sm">
              No exceptions recorded. All submissions clean!
            </div>
          ) : (
            <table className="min-w-full text-xs">
              <thead>
                <tr className="border-b bg-gray-50 text-left text-gray-500">
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3">Kind</th>
                  <th className="py-2 px-3">Event ID</th>
                  <th className="py-2 px-3">Source ID</th>
                  <th className="py-2 px-3">Reason / Details</th>
                  <th className="py-2 px-3">Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {exceptions.map((ex) => (
                  <tr key={ex.entry_id} className="border-b hover:bg-gray-50">
                    <td className="py-2 px-3">
                      <span
                        className={`badge ${
                          ex.status === 'PENDING_REFERENCE'
                            ? 'badge-pending'
                            : ex.status === 'CONFLICT'
                            ? 'badge-conflict'
                            : 'badge-rejected'
                        }`}
                      >
                        {ex.status}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-gray-500 font-mono text-[10px]">{ex.source_kind}</td>
                    <td className="py-2 px-3 font-mono">{ex.event_id || '-'}</td>
                    <td className="py-2 px-3">{ex.source_id || '-'}</td>
                    <td className="py-2 px-3 text-red-600 max-w-xs truncate" title={ex.reason || ''}>
                      {ex.reason || '-'}
                    </td>
                    <td className="py-2 px-3 text-gray-400">{new Date(ex.received_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};
