import React from 'react';
import { SummaryState } from '../api';

interface SummaryCardsProps {
  summary: SummaryState | null;
  loading: boolean;
}

export const SummaryCards: React.FC<SummaryCardsProps> = ({ summary, loading }) => {
  const cards = [
    { label: 'Net Total', value: summary?.net_total ?? 0, color: 'blue', desc: 'Valid accepted counts minus accepted voids' },
    { label: 'Processed Events', value: summary?.processed_events ?? 0, color: 'emerald', desc: 'Total accepted events' },
    { label: 'Pending Ack', value: summary?.pending_ack ?? 0, color: 'amber', desc: 'Accepted counts needing acknowledgment' },
    { label: 'Unresolved Voids', value: summary?.unresolved ?? 0, color: 'purple', desc: 'Voids waiting for target count event' },
    { label: 'Duplicates', value: summary?.duplicates ?? 0, color: 'slate', desc: 'Identical re-transmissions ignored' },
    { label: 'Conflicts', value: summary?.conflicts ?? 0, color: 'orange', desc: 'Conflicting event payloads rejected' },
    {
      label: 'Rejected Submissions',
      value: summary?.rejected_submissions ?? 0,
      color: 'red',
      desc: 'Invalid payloads & ceiling over 500',
      isAlert: true
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
      {cards.map((card) => (
        <div
          key={card.label}
          className={`card p-4 rounded-lg shadow-sm border-l-4 ${
            card.isAlert
              ? 'bg-red-50/60 border-red-500'
              : `bg-white border-${card.color}-500`
          }`}
        >
          <div
            className={`text-xs font-semibold uppercase tracking-wider ${
              card.isAlert ? 'text-red-700 font-bold' : 'text-gray-500'
            }`}
          >
            {card.label}
          </div>
          <div
            className={`text-2xl font-bold mt-1 ${
              card.isAlert ? 'text-red-700' : 'text-gray-900'
            }`}
          >
            {loading && !summary ? '...' : card.value.toLocaleString()}
          </div>
          <div
            className={`text-[11px] mt-1 truncate ${
              card.isAlert ? 'text-red-500 font-medium' : 'text-gray-400'
            }`}
            title={card.desc}
          >
            {card.desc}
          </div>
        </div>
      ))}
    </div>
  );
};
