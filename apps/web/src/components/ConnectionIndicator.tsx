import type { ConnectionStatus } from '../types/generated';

interface ConnectionIndicatorProps {
  status: ConnectionStatus;
}

const statusLabels: Record<ConnectionStatus, string> = {
  connecting: 'Connecting...',
  connected: 'Connected',
  disconnected: 'Disconnected',
  error: 'Error',
};

export default function ConnectionIndicator({ status }: ConnectionIndicatorProps) {
  return (
    <div className={`connection-indicator status-${status}`}>
      <span className="connection-dot" />
      <span className="connection-label">{statusLabels[status]}</span>
    </div>
  );
}
