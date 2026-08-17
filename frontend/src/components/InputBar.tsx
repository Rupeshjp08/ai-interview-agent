import { useState, useRef } from 'react';
import type { KeyboardEvent } from 'react';
import styles from './InputBar.module.css';

interface InputBarProps {
  onSend: (message: string) => void;
  isLoading: boolean;
  isComplete: boolean;
}

export function InputBar({ onSend, isLoading, isComplete }: InputBarProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSend = value.trim().length > 0 && !isLoading && !isComplete;

  const handleSend = () => {
    if (!canSend) return;
    onSend(value.trim());
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
    }
  };

  if (isComplete) {
    return (
      <div className={styles.completedBar}>
        <span className={styles.completedIcon}>🎉</span>
        <span>Interview complete — see your feedback above</span>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.inputWrap}>
        <textarea
          ref={textareaRef}
          id="interview-input"
          className={styles.textarea}
          placeholder="Type your answer… (Enter to send, Shift+Enter for new line)"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          disabled={isLoading || isComplete}
          rows={1}
          aria-label="Your answer"
        />
        <button
          id="send-message-btn"
          className={`${styles.sendBtn} ${canSend ? styles.active : ''}`}
          onClick={handleSend}
          disabled={!canSend}
          aria-label="Send message"
          type="button"
        >
          {isLoading ? (
            <span className={styles.spinner} aria-hidden="true" />
          ) : (
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M3 10l14-7-5 7 5 7-14-7z" fill="currentColor"/>
            </svg>
          )}
        </button>
      </div>
      <p className={styles.hint}>Enter to send · Shift+Enter for new line</p>
    </div>
  );
}
