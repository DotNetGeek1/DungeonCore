import { useRef, useEffect } from 'react';
import { useSession } from '../../context/SessionContext';
import MessageBubble from '../MessageBubble';

export default function PrivateMessagesPanel() {
  const { state } = useSession();
  const { messages } = state;
  const scrollRef = useRef<HTMLDivElement>(null);

  const privateMessages = messages.filter(
    (m) => m.channel === 'private_whisper' || m.visibility === 'private'
  );

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [privateMessages.length]);

  return (
    <div className="panel private-messages-panel">
      <h3 className="panel-title">Private Messages</h3>
      <div className="messages-content" ref={scrollRef}>
        {privateMessages.length === 0 ? (
          <p className="empty-state">No private messages.</p>
        ) : (
          privateMessages.map((message) => (
            <MessageBubble key={message.id} message={message} showRecipients />
          ))
        )}
      </div>
    </div>
  );
}
