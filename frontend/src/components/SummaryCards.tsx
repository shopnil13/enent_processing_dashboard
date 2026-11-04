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
    { label: 'Conflicts', value: summary?.conflicts ?? 0, color: 'rose', desc: 'Conflicting event payloads rejected' },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
      {cards.map((card) => (
        <div key={card.label} className={`card border-l-4 border-${card.color}-500 bg-white shadow-sm p-4 rounded-lg`}>
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{card.label}</div>
          <div className="text-2xl font-bold text-gray-900 mt-1">
            {loading && !summary ? '...' : card.value.toLocaleString()}
          </div>
          <div className="text-xs text-gray-400 mt-1 truncate" title={card.desc}>{card.desc}</div>
        </div>
      ))}
    </div>
  );
};
