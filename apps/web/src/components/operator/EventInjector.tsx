import { useState } from 'react';
import { useSession } from '../../context/SessionContext';
import { api } from '../../api/client';

interface EventInjectorProps {
  onClose: () => void;
}

const EVENT_TEMPLATES: Record<string, object> = {
  'state.updated': {
    patch: {
      flags: { test_flag: true },
    },
    reason: 'Manual injection for testing',
  },
  'message.created': {
    message: {
      id: 'injected-msg-1',
      turn_number: 0,
      phase: 'discussion',
      channel: 'dm_notice',
      sender_id: 'dm',
      sender_name: 'Dungeon Master',
      recipient_ids: 'all',
      visibility: 'public',
      text: 'This is an injected test message.',
      created_at: new Date().toISOString(),
    },
  },
  'narration.emitted': {
    narrator_id: 'dm',
    text: 'This is an injected narration for testing purposes.',
    style: 'dramatic',
  },
};

export default function EventInjector({ onClose }: EventInjectorProps) {
  const { state } = useSession();
  const { sessionId } = state;

  const [eventType, setEventType] = useState('state.updated');
  const [payloadJson, setPayloadJson] = useState(
    JSON.stringify(EVENT_TEMPLATES['state.updated'], null, 2)
  );
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<{ type: 'success' | 'error'; message: string } | null>(
    null
  );

  const handleEventTypeChange = (type: string) => {
    setEventType(type);
    if (EVENT_TEMPLATES[type]) {
      setPayloadJson(JSON.stringify(EVENT_TEMPLATES[type], null, 2));
    }
  };

  const handleInject = async () => {
    if (!sessionId) return;

    let payload: unknown;
    try {
      payload = JSON.parse(payloadJson);
    } catch {
      setResult({ type: 'error', message: 'Invalid JSON in payload' });
      return;
    }

    setIsLoading(true);
    setResult(null);

    try {
      const response = await api.injectEvent(sessionId, eventType, payload);
      if (response.accepted) {
        setResult({ type: 'success', message: 'Event injected successfully' });
      } else {
        setResult({ type: 'error', message: `Injection rejected: ${response.status}` });
      }
    } catch (err) {
      setResult({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to inject event',
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="event-injector">
      <div className="injector-header">
        <h4>Inject Test Event</h4>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>

      <div className="injector-form">
        <div className="form-row">
          <label htmlFor="event-type">Event Type</label>
          <select
            id="event-type"
            value={eventType}
            onChange={(e) => handleEventTypeChange(e.target.value)}
          >
            <option value="state.updated">state.updated</option>
            <option value="message.created">message.created</option>
            <option value="narration.emitted">narration.emitted</option>
            <option value="discussion.opened">discussion.opened</option>
            <option value="discussion.closed">discussion.closed</option>
          </select>
        </div>

        <div className="form-row">
          <label htmlFor="payload">Payload (JSON)</label>
          <textarea
            id="payload"
            className="payload-input"
            value={payloadJson}
            onChange={(e) => setPayloadJson(e.target.value)}
            rows={10}
          />
        </div>

        <div className="form-actions">
          <button
            className="toolbar-btn btn-inject-submit"
            onClick={handleInject}
            disabled={isLoading}
          >
            {isLoading ? 'Injecting...' : 'Inject Event'}
          </button>

          {result && (
            <span className={`inject-result result-${result.type}`}>
              {result.message}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
