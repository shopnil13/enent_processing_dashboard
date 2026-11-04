import React from 'react';
import { MqttStatus } from '../api';

interface MqttPanelProps {
  status: MqttStatus | null;
  loading: boolean;
}

export const MqttPanel: React.FC<MqttPanelProps> = ({ status, loading }) => {
  return (
    <div className="card bg-white p-5 rounded-lg shadow-sm mb-6 border border-gray-100">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 border-b pb-3">
        <div className="flex items-center gap-2">
          <span className="text-base font-bold text-gray-800">MQTT Challenge Worker</span>
          {status?.connected ? (
            <span className="flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-700">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
              ONLINE
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
              <span className="w-2 h-2 rounded-full bg-gray-400"></span>
              OFFLINE / CONNECTING
            </span>
          )}
        </div>
        <div className="text-xs text-gray-500 font-mono">
          Broker: {status?.broker || '152.42.238.142:1883'} | Candidate: <span className="font-semibold text-gray-800">{status?.candidate_id || '-'}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
        <div className="bg-gray-50 p-3 rounded">
          <div className="text-gray-500 font-medium">Completed Challenges</div>
          <div className="text-xl font-bold text-green-600 mt-1">
            {loading && !status ? '...' : status?.completed_challenges ?? 0}
          </div>
          <div className="text-[10px] text-gray-400 mt-0.5">Durable count</div>
        </div>

        <div className="bg-gray-50 p-3 rounded">
          <div className="text-gray-500 font-medium">Failed Challenges</div>
          <div className="text-xl font-bold text-red-500 mt-1">
            {loading && !status ? '...' : status?.failed_challenges ?? 0}
          </div>
          <div className="text-[10px] text-gray-400 mt-0.5">Durable count</div>
        </div>

        <div className="bg-gray-50 p-3 rounded">
          <div className="text-gray-500 font-medium">Last Challenge ID</div>
          <div className="font-mono text-gray-800 font-semibold truncate mt-1">
            {status?.last_challenge_id || 'None yet'}
          </div>
          <div className="text-[10px] text-gray-400 mt-0.5">
            {status?.last_challenge_time ? new Date(status.last_challenge_time).toLocaleTimeString() : '-'}
          </div>
        </div>

        <div className="bg-gray-50 p-3 rounded">
          <div className="text-gray-500 font-medium">Last Result / Error</div>
          <div className="font-semibold mt-1">
            {status?.last_response_status === 'COMPLETED' ? (
              <span className="text-green-600">COMPLETED</span>
            ) : status?.last_response_status === 'FAILED' ? (
              <span className="text-red-600">FAILED: {status.last_error}</span>
            ) : (
              <span className="text-gray-400">Idle</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
