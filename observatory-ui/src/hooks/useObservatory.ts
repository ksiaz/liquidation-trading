import { useQuery } from '@tanstack/react-query';
import type { Mandate, Zone, Liquidation, Stability, Health, ObservatorySnapshot, ArbitrationRound } from '../types/observatory';

const API_BASE = '/api';

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`Failed to fetch ${path}: ${res.status}`);
  return res.json();
}

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: () => fetchJSON<Health>('/health'), refetchInterval: 10000 });
}

export function useStability() {
  return useQuery({ queryKey: ['stability'], queryFn: () => fetchJSON<Stability>('/stability'), refetchInterval: 5000 });
}

export function useSnapshot() {
  return useQuery({ queryKey: ['snapshot'], queryFn: () => fetchJSON<ObservatorySnapshot>('/snapshot'), refetchInterval: 5000 });
}

export function useMandates(options?: { symbol?: string; mandateType?: string; limit?: number }) {
  const params = new URLSearchParams();
  if (options?.symbol) params.set('symbol', options.symbol);
  if (options?.mandateType) params.set('mandate_type', options.mandateType);
  if (options?.limit) params.set('limit', String(options.limit));
  const query = params.toString();
  return useQuery({ queryKey: ['mandates', options], queryFn: () => fetchJSON<Mandate[]>(`/mandates${query ? `?${query}` : ''}`), refetchInterval: 5000 });
}

export function useArbitration(options?: { symbol?: string; limit?: number }) {
  const params = new URLSearchParams();
  if (options?.symbol) params.set('symbol', options.symbol);
  if (options?.limit) params.set('limit', String(options.limit));
  const query = params.toString();
  return useQuery({ queryKey: ['arbitration', options], queryFn: () => fetchJSON<ArbitrationRound[]>(`/arbitration${query ? `?${query}` : ''}`), refetchInterval: 5000 });
}

export function useZones(symbol?: string) {
  return useQuery({ queryKey: ['zones', symbol], queryFn: () => fetchJSON<Zone[]>(symbol ? `/zones?symbol=${symbol}` : '/zones'), refetchInterval: 10000 });
}

export function useLiquidations(options?: { symbol?: string; side?: string; limit?: number }) {
  const params = new URLSearchParams();
  if (options?.symbol) params.set('symbol', options.symbol);
  if (options?.side) params.set('side', options.side);
  if (options?.limit) params.set('limit', String(options.limit));
  const query = params.toString();
  return useQuery({ queryKey: ['liquidations', options], queryFn: () => fetchJSON<Liquidation[]>(`/liquidations${query ? `?${query}` : ''}`), refetchInterval: 5000 });
}

export function formatTimestamp(ts: number): string { return new Date(ts * 1000).toLocaleString(); }
export function formatUSD(val: number | null): string { return val != null ? `$${val.toLocaleString()}` : '-'; }
export function formatNumber(val: number | null, decimals = 2): string { return val != null ? val.toFixed(decimals) : '-'; }
export function formatUptime(sec: number): string { const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60); return h > 0 ? `${h}h ${m}m` : `${m}m`; }
