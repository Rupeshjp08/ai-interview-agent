import { useState } from 'react';
import styles from './CandidateSetup.module.css';
import type { CandidateSummary } from '../types/interview';

interface CandidateSetupProps {
  onStart: (candidateId: string) => void;
  isLoading: boolean;
  candidates: CandidateSummary[];
  candidatesLoading: boolean;
}

const DIFFICULTY_LABELS: Record<string, string> = {
  beginner: '🟢 Beginner',
  intermediate: '🟡 Intermediate',
  advanced: '🔴 Advanced',
};

export function CandidateSetup({
  onStart,
  isLoading,
  candidates,
  candidatesLoading,
}: CandidateSetupProps) {
  const [selectedId, setSelectedId] = useState<string>('');
  const [customId, setCustomId] = useState('');
  const [useCustom, setUseCustom] = useState(false);

  // Resolve effective candidate ID
  const firstId = candidates[0]?.candidate_id ?? '';
  const resolvedId = useCustom ? customId.trim() : (selectedId || firstId);
  const canStart = !isLoading && resolvedId.length > 0 && !candidatesLoading;

  const handleStart = () => {
    if (canStart) onStart(resolvedId);
  };

  const handleSelectPreset = (id: string) => {
    setSelectedId(id);
    setUseCustom(false);
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        {/* Logo / Hero */}
        <div className={styles.hero}>
          <div className={styles.orb} aria-hidden="true" />
          <div className={styles.iconWrap}>
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <circle cx="24" cy="24" r="22" stroke="url(#g1)" strokeWidth="2" />
              <path d="M14 24c0-5.523 4.477-10 10-10s10 4.477 10 10-4.477 10-10 10" stroke="url(#g2)" strokeWidth="2.5" strokeLinecap="round" />
              <circle cx="24" cy="24" r="4" fill="url(#g1)" />
              <defs>
                <linearGradient id="g1" x1="2" y1="2" x2="46" y2="46" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#a78bfa" /><stop offset="1" stopColor="#38bdf8" />
                </linearGradient>
                <linearGradient id="g2" x1="14" y1="14" x2="34" y2="34" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#818cf8" /><stop offset="1" stopColor="#34d399" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h1 className={styles.title}>AI Interview Agent</h1>
          <p className={styles.subtitle}>
            Your personalised technical interview powered by Google Gemini
          </p>
        </div>

        {/* Feature pills */}
        <div className={styles.pills}>
          <span className={styles.pill}>🎯 Adaptive Questions</span>
          <span className={styles.pill}>🧠 Gemini AI</span>
          <span className={styles.pill}>📋 Structured Feedback</span>
        </div>

        {/* Candidate selection */}
        <div className={styles.form}>
          <label className={styles.label}>Select Candidate Profile</label>

          {candidatesLoading ? (
            <div className={styles.loadingCandidates}>
              <span className={styles.loadingSpinner} aria-label="Loading candidates" />
              <span>Loading candidates…</span>
            </div>
          ) : (
            <div className={styles.optionGroup}>
              {candidates.map((c) => {
                const isSelected = !useCustom && resolvedId === c.candidate_id;
                return (
                  <button
                    key={c.candidate_id}
                    id={`candidate-btn-${c.candidate_id}`}
                    className={`${styles.optionBtn} ${isSelected ? styles.selected : ''}`}
                    onClick={() => handleSelectPreset(c.candidate_id)}
                    type="button"
                  >
                    <span className={styles.optionIcon}>👤</span>
                    <span className={styles.optionTextBlock}>
                      <span className={styles.optionName}>{c.name}</span>
                      <span className={styles.optionMeta}>
                        {c.cohort} · {c.days_completed} days ·{' '}
                        {DIFFICULTY_LABELS[c.interview_difficulty ?? 'intermediate'] ?? '🟡 Intermediate'}
                      </span>
                    </span>
                    {isSelected && <span className={styles.checkmark}>✓</span>}
                  </button>
                );
              })}

              {candidates.length === 0 && (
                <p className={styles.noCandidates}>
                  No candidates found. Check the backend is running and has profiles in{' '}
                  <code>data/candidates/</code>.
                </p>
              )}

              <button
                id="candidate-btn-custom"
                className={`${styles.optionBtn} ${useCustom ? styles.selected : ''}`}
                onClick={() => setUseCustom(true)}
                type="button"
              >
                <span className={styles.optionIcon}>✏️</span>
                <span className={styles.optionTextBlock}>
                  <span className={styles.optionName}>Enter custom candidate ID</span>
                  <span className={styles.optionMeta}>For testing or adding new candidates</span>
                </span>
                {useCustom && <span className={styles.checkmark}>✓</span>}
              </button>
            </div>
          )}

          {useCustom && (
            <input
              id="custom-candidate-id"
              className={styles.input}
              type="text"
              placeholder="e.g. candidate_002"
              value={customId}
              onChange={(e) => setCustomId(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleStart()}
              autoFocus
            />
          )}

          <button
            id="start-interview-btn"
            className={styles.startBtn}
            onClick={handleStart}
            disabled={!canStart}
            type="button"
          >
            {isLoading ? (
              <span className={styles.spinner} aria-label="Starting interview…" />
            ) : (
              <>
                <span>Begin Interview</span>
                <span className={styles.arrow}>→</span>
              </>
            )}
          </button>
        </div>

        <p className={styles.note}>
          The interview consists of 8+ adaptive questions based on your 31-day cohort curriculum.
        </p>
      </div>
    </div>
  );
}
