/**
 * api.ts — Centralised API client for the AI Interview Agent.
 *
 * In development: requests go to the Vite dev proxy (relative paths).
 *   The proxy forwards /api/* → http://localhost:8000/api/*
 *   No CORS issues since both origin and target appear as localhost:5173.
 *
 * In production: set VITE_API_URL env var to the backend's absolute URL.
 *   e.g. VITE_API_URL=https://api.myapp.com
 */

import type {
  InterviewRequest,
  InterviewResponse,
  CandidateSummary,
} from './interview';

// ---------------------------------------------------------------------------
// Base URL
// ---------------------------------------------------------------------------
// Empty string = use relative paths (works with Vite proxy in dev).
// In production, set VITE_API_URL to the absolute backend URL.
const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined) ?? '';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ApiError {
  /** HTTP status code */
  status: number;
  /** Human-readable message from the server */
  message: string;
}

export interface CandidateListResponse {
  candidates: CandidateSummary[];
  total: number;
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

async function parseErrorBody(res: Response): Promise<string> {
  try {
    const body = await res.json() as { detail?: string };
    return body.detail ?? `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status} — ${res.statusText}`;
  }
}

async function fetchJSON<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    },
    ...options,
  });

  if (!res.ok) {
    const message = await parseErrorBody(res);
    const err: ApiError = { status: res.status, message };
    throw err;
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Public API functions
// ---------------------------------------------------------------------------

/** GET /api/candidates — list all available candidate profiles */
export async function fetchCandidates(): Promise<CandidateListResponse> {
  return fetchJSON<CandidateListResponse>('/api/candidates');
}

/** GET /api/candidates/{id} — get a single candidate's full profile */
export async function fetchCandidate(
  candidateId: string,
): Promise<Record<string, unknown>> {
  return fetchJSON<Record<string, unknown>>(`/api/candidates/${candidateId}`);
}

/** POST /api/interview — drive one interview turn */
export async function postInterviewTurn(
  payload: InterviewRequest,
  signal?: AbortSignal,
): Promise<InterviewResponse> {
  return fetchJSON<InterviewResponse>('/api/interview', {
    method: 'POST',
    body: JSON.stringify(payload),
    signal,
  });
}

/** GET /health — detailed health check */
export async function fetchHealth(): Promise<{
  status: string;
  google_api_configured: boolean;
  version: string;
}> {
  return fetchJSON('/health');
}
