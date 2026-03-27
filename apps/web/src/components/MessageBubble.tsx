import type { TableMessage } from '../types/generated';

interface MessageBubbleProps {
  message: TableMessage;
  compact?: boolean;
  showRecipients?: boolean;
}

export default function MessageBubble({
  message,
  compact = false,
  showRecipients = false,
}: MessageBubbleProps) {
  const channelClass = `channel-${message.channel.replace('_', '-')}`;
  const visibilityClass = `visibility-${message.visibility.replace('_', '-')}`;

  const formattedTime = new Date(message.created_at).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <div className={`message-bubble ${channelClass} ${visibilityClass} ${compact ? 'compact' : ''}`}>
      <div className="message-header">
        <span className="message-sender">{message.sender_name}</span>
        {!compact && (
          <>
            <span className="message-channel">{formatChannel(message.channel)}</span>
            <span className="message-time">{formattedTime}</span>
          </>
        )}
      </div>

      <div className="message-content">
        <p className="message-text">{message.text}</p>
      </div>

      {showRecipients && message.recipient_ids !== 'all' && (
        <div className="message-recipients">
          To: {message.recipient_ids.join(', ')}
        </div>
      )}

      {compact && <span className="message-time-compact">{formattedTime}</span>}
    </div>
  );
}

function formatChannel(channel: string): string {
  switch (channel) {
    case 'in_character':
      return 'IC';
    case 'table_talk':
      return 'OOC';
    case 'private_whisper':
      return 'Whisper';
    case 'dm_notice':
      return 'DM';
    default:
      return channel;
  }
}
