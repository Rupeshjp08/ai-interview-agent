import { useState, useEffect } from 'react';
import { useInterview } from './hooks/useInterview';
import { CandidateSetup } from './components/CandidateSetup';
import { ChatWindow } from './components/ChatWindow';
import { InputBar } from './components/InputBar';
import { FeedbackPanel } from './components/FeedbackPanel';
import styles from './App.module.css';

type AppView = 'setup' | 'interview';

function App() {
  const [view, setView] = useState<AppView>('setup');

  const {
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
  } = useInterview();

  // Auto-dismiss errors after 8 seconds
  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => clearError(), 8000);
    return () => clearTimeout(timer);
  }, [error, clearError]);

  const handleStart = async (candidateId: string) => {
    await startInterview(candidateId);
    setView('interview');
  };

  const handleRestart = () => {
    resetInterview();
    setView('setup');
  };

  return (
    <div className={styles.app}>
      {view === 'setup' && (
        <CandidateSetup
          onStart={handleStart}
          isLoading={isLoading}
          candidates={candidates}
          candidatesLoading={candidatesLoading}
        />
      )}

      {view === 'interview' && (
        <div className={styles.interviewLayout}>
          <ChatWindow
            messages={messages}
            isLoading={isLoading}
            questionCount={questionCount}
            candidateName={candidateName}
          />
          <InputBar
            onSend={sendMessage}
            isLoading={isLoading}
            isComplete={isComplete}
          />
        </div>
      )}

      {/* Feedback overlay */}
      {isComplete && feedback && (
        <FeedbackPanel
          feedback={feedback}
          candidateName={candidateName}
          onRestart={handleRestart}
        />
      )}

      {/* Error toast — auto-dismisses after 8s, or manually via × */}
      {error && (
        <div className={styles.errorToast} role="alert" aria-live="assertive">
          <span>⚠️ {error}</span>
          <button
            className={styles.errorClose}
            onClick={clearError}
            aria-label="Dismiss error"
            type="button"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}

export default App;
