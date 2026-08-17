/**
 * useInterview.ts
 * ================
 * Core React hook that drives the entire interview lifecycle.
 *
 * Features:
 * - Dynamic candidate list loaded from the API
 * - Automatic retry on transient server errors (503, 429, network failures)
 * - AbortController to cancel in-flight requests on component unmount
 * - Typed error state with user-facing messages
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { fetchCandidates, postInterviewTurn, type ApiError, type CandidateListResponse } from '../types/api';
import type {
  ChatMessage,
  InterviewFeedback,
  CandidateSummary,
} from '../types/interview';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UseInterviewReturn {
  /** All chat messages in chronological order */
  messages: ChatMessage[];
  /** True while an API call is in flight */
  isLoading: boolean;
  /** True after the interview is finished */
  isComplete: boolean;
  /** Structured feedback — only set when isComplete is true */
  feedback: InterviewFeedback | null;
  /** Number of questions asked so far */
  questionCount: number;
  /** Candidate name from the server */
  candidateName: string | null;
  /** Error message to show in the UI (null = no error) */
  error: string | null;
  /** Available candidates fetched from the API */
  candidates: CandidateSummary[];
  /** True while the candidate list is loading */
  candidatesLoading: boolean;
  /** Start a new interview for the given candidateId */
  startInterview: (candidateId: string) => Promise<void>;
  /** Send the user's answer and get the next question */
  sendMessage: (userMessage: string) => Promise<void>;
  /** Reset all state to go back to the setup screen */
  resetInterview: () => void;
  /** Dismiss the current error toast */
  clearError: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_RETRIES = 2;
const RETRYABLE_STATUSES = new Set([429, 503, 502, 504]);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isRetryableError(err: unknown): boolean {
  if (err instanceof Error && err.name === 'AbortError') return false;
  const apiErr = err as Partial<ApiError>;
  return (
    apiErr.status === undefined || // network error — no status
    RETRYABLE_STATUSES.has(apiErr.status ?? 0)
  );
}

function makeMessage(role: ChatMessage['role'], content: string): ChatMessage {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    role,
    content,
    timestamp: new Date(),
  };
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useInterview(): UseInterviewReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [feedback, setFeedback] = useState<InterviewFeedback | null>(null);
  const [questionCount, setQuestionCount] = useState(0);
  const [candidateName, setCandidateName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(true);

  const sessionIdRef = useRef<string | null>(null);
  const candidateIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ─── Load candidates on mount ───────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    async function loadCandidates(): Promise<void> {
      try {
        const data: CandidateListResponse = await fetchCandidates();
        if (!cancelled) {
          setCandidates(data.candidates);
        }
      } catch {
        // Silently fail — the setup screen will show a fallback
        if (!cancelled) {
          setCandidates([]);
        }
      } finally {
        if (!cancelled) {
          setCandidatesLoading(false);
        }
      }
    }

    void loadCandidates();
    return () => { cancelled = true; };
  }, []);

  // ─── Abort any in-flight request on unmount ──────────────────────────────
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // ─── Helpers ─────────────────────────────────────────────────────────────

  const addMessage = useCallback((role: ChatMessage['role'], content: string) => {
    const msg = makeMessage(role, content);
    setMessages((prev) => [...prev, msg]);
    return msg;
  }, []);

  /**
   * Call the interview API with automatic retry on transient errors.
   * Uses exponential backoff: 1s → 2s.
   */
  const callWithRetry = useCallback(
    async (
      payload: Parameters<typeof postInterviewTurn>[0],
      signal: AbortSignal,
    ) => {
      let lastErr: unknown;
      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        try {
          return await postInterviewTurn(payload, signal);
        } catch (err) {
          lastErr = err;
          if (!isRetryableError(err) || attempt === MAX_RETRIES) throw err;
          // Exponential backoff: 1s, 2s, ...
          await sleep(1000 * Math.pow(2, attempt));
        }
      }
      throw lastErr;
    },
    [],
  );

  // ─── startInterview ───────────────────────────────────────────────────────

  const startInterview = useCallback(
    async (candidateId: string) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      setIsLoading(true);
      setError(null);
      candidateIdRef.current = candidateId;

      try {
        const data = await callWithRetry(
          { candidate_id: candidateId },
          ctrl.signal,
        );
        sessionIdRef.current = data.session_id;
        addMessage('interviewer', data.message);
        setQuestionCount(data.metadata?.question_count ?? 0);
        setCandidateName(data.metadata?.candidate_name ?? null);

        if (data.is_complete) {
          setIsComplete(true);
          setFeedback(data.feedback);
        }
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return;
        const apiErr = err as Partial<ApiError>;
        setError(
          apiErr.message ??
            'Failed to start the interview. Is the backend running?',
        );
      } finally {
        setIsLoading(false);
      }
    },
    [addMessage, callWithRetry],
  );

  // ─── sendMessage ──────────────────────────────────────────────────────────

  const sendMessage = useCallback(
    async (userMessage: string) => {
      if (!sessionIdRef.current || !candidateIdRef.current) return;

      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      addMessage('candidate', userMessage);
      setIsLoading(true);
      setError(null);

      try {
        const data = await callWithRetry(
          {
            session_id: sessionIdRef.current,
            candidate_id: candidateIdRef.current,
            user_message: userMessage,
          },
          ctrl.signal,
        );

        addMessage('interviewer', data.message);
        setQuestionCount(data.metadata?.question_count ?? 0);

        if (data.is_complete) {
          setIsComplete(true);
          setFeedback(data.feedback);
        }
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return;
        const apiErr = err as Partial<ApiError>;
        setError(
          apiErr.message ?? 'Failed to send message. Please try again.',
        );
      } finally {
        setIsLoading(false);
      }
    },
    [addMessage, callWithRetry],
  );

  // ─── resetInterview ───────────────────────────────────────────────────────

  const resetInterview = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setIsLoading(false);
    setIsComplete(false);
    setFeedback(null);
    setQuestionCount(0);
    setCandidateName(null);
    setError(null);
    sessionIdRef.current = null;
    candidateIdRef.current = null;
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return {
    messages,
    isLoading,
    isComplete,
    feedback,
    questionCount,
    candidateName,
    error,
    candidates,
    candidatesLoading,
    startInterview,
    sendMessage,
    resetInterview,
    clearError,
  };
}
