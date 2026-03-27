import { useState } from 'react';
import { useSession } from '../../context/SessionContext';
import { api } from '../../api/client';

interface DiscussionInputProps {
  actorId: string;
}

export default function DiscussionInput({ actorId }: DiscussionInputProps) {
  const { state } = useSession();
  const { sessionId, gameState } = state;

  const [text, setText] = useState('');
  const [channel, setChannel] = useState<'speech' | 'table_talk'>('speech');
  const [isSending, setIsSending] = useState(false);

  const isDiscussionOpen = gameState?.turn?.discussion_open ?? false;
  const remaining = gameState?.turn?.remaining_discussion_messages ?? 0;

  const handleSend = async () => {
    if (!sessionId || !text.trim()) return;
    setIsSending(true);

    const turn = channel === 'speech'
      ? { speech: text.trim() }
      : { table_talk: text.trim() };

    try {
      await api.submitAction(sessionId, actorId, turn);
      setText('');
    } catch (err) {
      console.error('Failed to send message:', err);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="panel discussion-input-panel">
      <h3>Discussion</h3>

      {!isDiscussionOpen && (
        <p className="waiting-message">Discussion is not open right now.</p>
      )}

      <div className="form-group">
        <div className="channel-toggle">
          <button
            className={`toggle-btn ${channel === 'speech' ? 'active' : ''}`}
            onClick={() => setChannel('speech')}
          >
            In-Character
          </button>
          <button
            className={`toggle-btn ${channel === 'table_talk' ? 'active' : ''}`}
            onClick={() => setChannel('table_talk')}
          >
            Table Talk
          </button>
        </div>
      </div>

      <div className="form-group">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={
            channel === 'speech'
              ? 'Speak in character...'
              : 'Tactical suggestion...'
          }
          rows={3}
          disabled={!isDiscussionOpen || isSending}
          maxLength={280}
        />
        <span className="char-count">{text.length}/280</span>
      </div>

      <button
        className="btn-send-message"
        onClick={handleSend}
        disabled={!isDiscussionOpen || isSending || !text.trim()}
      >
        {isSending ? 'Sending...' : 'Send'}
      </button>

      {remaining > 0 && (
        <span className="messages-remaining">{remaining} messages remaining</span>
      )}
    </div>
  );
}
