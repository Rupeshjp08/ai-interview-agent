/**
 * TypeScript types for the AI Interview Agent API.
 */

// ---------------------------------------------------------------------------
// Interview request / response
// ---------------------------------------------------------------------------

export interface InterviewRequest {
  session_id?: string;
  candidate_id: string;
  user_message?: string;
}

export interface FeedbackTopicScores {
  [topic: string]: number;
}

export interface InterviewFeedback {
  overall_score: number;
  summary: string;
  strengths_demonstrated: string[];
  areas_for_improvement: string[];
  topic_scores: FeedbackTopicScores;
  recommendation: 'Hire' | 'Strong Hire' | 'No Hire' | 'Maybe';
}

export interface InterviewResponse {
  session_id: string;
  message: string;
  is_complete: boolean;
  feedback: InterviewFeedback | null;
  metadata: {
    question_count?: number;
    days_covered?: number;
    candidate_name?: string;
    can_complete?: boolean;
    [key: string]: unknown;
  } | null;
}

// ---------------------------------------------------------------------------
// Candidate types
// ---------------------------------------------------------------------------

export interface CandidateSummary {
  candidate_id: string;
  name: string;
  cohort: string;
  days_completed: number;
  interview_difficulty?: string;
  strengths: string[];
  weak_areas: string[];
}

// ---------------------------------------------------------------------------
// Chat message types
// ---------------------------------------------------------------------------

export type MessageRole = 'interviewer' | 'candidate';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
}
