import { useEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';
import styles from './ChatWindow.module.css';
import type { ChatMessage } from '../types/interview';

interface ChatWindowProps {
  messages: ChatMessage[];
  isLoading: boolean;
  questionCount: number;
  candidateName: string | null;
}

export function ChatWindow({
  messages,
  isLoading,
  questionCount,
  candidateName,
}: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.statusDot} aria-label="Live" />
          <div>
            <h2 className={styles.headerTitle}>Technical Interview</h2>
            {candidateName && (
              <p className={styles.headerSub}>Candidate: {candidateName}</p>
            )}
          </div>
        </div>
        <div className={styles.headerRight}>
          <span className={styles.questionBadge}>
            Q {questionCount} / 8+
          </span>
        </div>
      </div>

      {/* Messages */}
      <div className={styles.messageList} role="log" aria-live="polite" aria-label="Interview conversation">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {isLoading && (
          <div className={styles.typingIndicator} aria-label="AI is thinking">
            <div className={styles.typingDot} />
            <div className={styles.typingDot} />
            <div className={styles.typingDot} />
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
