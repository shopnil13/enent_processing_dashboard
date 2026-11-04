export interface SummaryState {
  net_total: number;
  processed_events: number;
  pending_ack: number;
  unresolved: number;
  duplicates: number;
  conflicts: number;
  rejected_submissions: number;
}

export interface PendingEvent {
  id: number;
  source_id: string;
  event_id: string;
  type: string;
  quantity: number | null;
  target_event_id: string | null;
  event_time: string;
  received_at: string;
  status: string;
}

export interface SystemException {
  entry_id: string;
  source_id: string | null;
  event_id: string | null;
  type: string;
  status: string;
  reason: string | null;
  received_at: string;
  source_kind: 'EVENT' | 'ATTEMPT';
}

export interface ItemResult {
  status: 'ACCEPTED' | 'DUPLICATE' | 'CONFLICT' | 'PENDING_REFERENCE' | 'REJECTED';
  event_id: string | null;
  source_id: string | null;
  reason?: string;
}

export interface AckResult {
  event_id: string;
  status: 'ACKED' | 'ALREADY_ACKED' | 'NOT_READY' | 'NOT_FOUND';
}

export interface MqttStatus {
  connected: boolean;
  candidate_id: string;
  broker: string;
  last_challenge_id: string | null;
  last_challenge_time: string | null;
  last_response_status: string | null;
  last_error: string | null;
  completed_challenges: number;
  failed_challenges: number;
}

const API_BASE = '/api';

export async function fetchSummary(sourceId?: string): Promise<SummaryState> {
  const query = new URLSearchParams({ view: 'summary' });
  if (sourceId && sourceId.trim()) query.append('source_id', sourceId.trim());
  const res = await fetch(`${API_BASE}/state?${query.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch summary: ${res.statusText}`);
  return res.json();
}

export async function fetchPending(sourceId?: string): Promise<PendingEvent[]> {
  const query = new URLSearchParams({ view: 'pending' });
  if (sourceId && sourceId.trim()) query.append('source_id', sourceId.trim());
  const res = await fetch(`${API_BASE}/state?${query.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch pending events: ${res.statusText}`);
  const data = await res.json();
  return data.events || [];
}

export async function fetchExceptions(sourceId?: string): Promise<SystemException[]> {
  const query = new URLSearchParams({ view: 'exceptions' });
  if (sourceId && sourceId.trim()) query.append('source_id', sourceId.trim());
  const res = await fetch(`${API_BASE}/state?${query.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch exceptions: ${res.statusText}`);
  const data = await res.json();
  return data.exceptions || [];
}

export async function fetchSources(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/state?view=sources`);
  if (!res.ok) throw new Error(`Failed to fetch sources: ${res.statusText}`);
  const data = await res.json();
  return data.sources || [];
}

export async function fetchMqttStatus(): Promise<MqttStatus> {
  const res = await fetch(`${API_BASE}/state?view=mqtt`);
  if (!res.ok) throw new Error(`Failed to fetch MQTT status: ${res.statusText}`);
  return res.json();
}

export async function submitEvents(payload: any): Promise<ItemResult[]> {
  const res = await fetch(`${API_BASE}/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  const data = await res.json();
  return data.results || [];
}

export async function acknowledgeEvents(eventIds: string[]): Promise<AckResult[]> {
  const res = await fetch(`${API_BASE}/ack`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event_ids: eventIds }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  const data = await res.json();
  return data.results || [];
}
