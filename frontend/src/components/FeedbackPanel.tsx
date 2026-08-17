import styles from './FeedbackPanel.module.css';
import type { InterviewFeedback } from '../types/interview';

interface FeedbackPanelProps {
  feedback: InterviewFeedback;
  candidateName: string | null;
  onRestart: () => void;
}

const RECOMMENDATION_CONFIG: Record<
  string,
  { color: string; emoji: string }
> = {
  'Strong Hire': { color: '#34d399', emoji: '🚀' },
  'Hire': { color: '#60a5fa', emoji: '✅' },
  'Maybe': { color: '#fbbf24', emoji: '🤔' },
  'No Hire': { color: '#f87171', emoji: '❌' },
};

function ScoreBar({ score, label }: { score: number; label: string }) {
  const pct = (score / 10) * 100;
  const color =
    score >= 8 ? '#34d399' : score >= 6 ? '#60a5fa' : score >= 4 ? '#fbbf24' : '#f87171';

  return (
    <div className={styles.scoreBar}>
      <div className={styles.scoreLabel}>
        <span>{label}</span>
        <span className={styles.scoreNum} style={{ color }}>{score}/10</span>
      </div>
      <div className={styles.scoreTrack}>
        <div
          className={styles.scoreFill}
          style={{ width: `${pct}%`, background: color }}
          role="progressbar"
          aria-valuenow={score}
          aria-valuemin={0}
          aria-valuemax={10}
          aria-label={`${label}: ${score} out of 10`}
        />
      </div>
    </div>
  );
}

export function FeedbackPanel({ feedback, candidateName, onRestart }: FeedbackPanelProps) {
  const rec = RECOMMENDATION_CONFIG[feedback.recommendation] ?? {
    color: '#a78bfa',
    emoji: '📊',
  };

  return (
    <div className={styles.overlay}>
      <div className={styles.panel}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerGlow} aria-hidden="true" />
          <span className={styles.completeBadge}>Interview Complete</span>
          <h2 className={styles.title}>
            {candidateName ? `${candidateName}'s Results` : 'Your Results'}
          </h2>

          {/* Overall score ring */}
          <div className={styles.scoreRing} aria-label={`Overall score: ${feedback.overall_score} out of 10`}>
            <svg width="120" height="120" viewBox="0 0 120 120" aria-hidden="true">
              <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10"/>
              <circle
                cx="60" cy="60" r="50"
                fill="none"
                stroke="url(#scoreGrad)"
                strokeWidth="10"
                strokeLinecap="round"
                strokeDasharray={`${2 * Math.PI * 50}`}
                strokeDashoffset={`${2 * Math.PI * 50 * (1 - feedback.overall_score / 10)}`}
                transform="rotate(-90 60 60)"
              />
              <defs>
                <linearGradient id="scoreGrad" x1="0" y1="0" x2="1" y2="1">
                  <stop stopColor="#a78bfa"/><stop offset="1" stopColor="#38bdf8"/>
                </linearGradient>
              </defs>
            </svg>
            <div className={styles.scoreText}>
              <span className={styles.scoreValue}>{feedback.overall_score}</span>
              <span className={styles.scoreMax}>/10</span>
            </div>
          </div>

          {/* Recommendation badge */}
          <div className={styles.recommendation} style={{ borderColor: rec.color, color: rec.color }}>
            <span>{rec.emoji}</span>
            <span>{feedback.recommendation}</span>
          </div>
        </div>

        {/* Summary */}
        <div className={styles.section}>
          <p className={styles.summary}>{feedback.summary}</p>
        </div>

        {/* Strengths & Improvements */}
        <div className={styles.twoCol}>
          <div className={styles.column}>
            <h3 className={styles.columnTitle}>
              <span className={styles.columnIcon}>💪</span> Strengths
            </h3>
            <ul className={styles.list}>
              {feedback.strengths_demonstrated.map((s, i) => (
                <li key={i} className={`${styles.listItem} ${styles.strength}`}>{s}</li>
              ))}
            </ul>
          </div>
          <div className={styles.column}>
            <h3 className={styles.columnTitle}>
              <span className={styles.columnIcon}>📈</span> To Improve
            </h3>
            <ul className={styles.list}>
              {feedback.areas_for_improvement.map((a, i) => (
                <li key={i} className={`${styles.listItem} ${styles.improvement}`}>{a}</li>
              ))}
            </ul>
          </div>
        </div>

        {/* Topic scores */}
        {Object.keys(feedback.topic_scores).length > 0 && (
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Topic Breakdown</h3>
            <div className={styles.scoresList}>
              {Object.entries(feedback.topic_scores).map(([topic, score]) => (
                <ScoreBar key={topic} label={topic} score={score} />
              ))}
            </div>
          </div>
        )}

        {/* Restart */}
        <button
          id="restart-interview-btn"
          className={styles.restartBtn}
          onClick={onRestart}
          type="button"
        >
          Start New Interview
        </button>
      </div>
    </div>
  );
}
