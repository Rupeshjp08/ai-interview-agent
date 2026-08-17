import styles from './MessageBubble.module.css';
import type { ChatMessage } from '../types/interview';

interface MessageBubbleProps {
  message: ChatMessage;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isInterviewer = message.role === 'interviewer';

  return (
    <div className={`${styles.wrapper} ${isInterviewer ? styles.interviewerWrapper : styles.candidateWrapper}`}>
      {isInterviewer && (
        <div className={styles.avatar} aria-label="AI Interviewer">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <circle cx="10" cy="10" r="9" stroke="url(#ag)" strokeWidth="1.5"/>
            <circle cx="10" cy="10" r="3" fill="url(#ag)"/>
            <defs>
              <linearGradient id="ag" x1="1" y1="1" x2="19" y2="19" gradientUnits="userSpaceOnUse">
                <stop stopColor="#a78bfa"/><stop offset="1" stopColor="#38bdf8"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
      )}

      <div className={`${styles.bubble} ${isInterviewer ? styles.interviewerBubble : styles.candidateBubble}`}>
        {isInterviewer && (
          <span className={styles.senderLabel}>AI Interviewer</span>
        )}
        <p className={styles.content}>{message.content}</p>
        <span className={styles.timestamp}>{formatTime(message.timestamp)}</span>
      </div>

      {!isInterviewer && (
        <div className={styles.avatar} aria-label="You">
          <span>You</span>
        </div>
      )}
    </div>
  );
}
