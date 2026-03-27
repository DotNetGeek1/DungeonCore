import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../../context/SessionContext';
import { api } from '../../api/client';
import type { GameEvent, EventType } from '../../types/generated';

const EVENT_TYPE_OPTIONS: EventType[] = [
  'session.started',
  'scene.started',
  'discussion.opened',
  'discussion.closed',
  'message.created',
  'action.proposed',
  'action.validated',
  'action.awaiting_human',
  'action.resolved',
  'dice.rolled',
  'state.updated',
  'narration.emitted',
  'takeover.changed',
  'turn.ended',
];

export default function EventDebugPanel() {
  const { state, dispatch } = useSession();
  const { events, sessionId } = state;
  const navigate = useNavigate();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>('');
  const [filterTurn, setFilterTurn] = useState<string>('');
  const [hasBackfilled, setHasBackfilled] = useState(false);

  useEffect(() => {
    if (sessionId && !hasBackfilled) {
      api.getEvents(sessionId, { limit: 500 })
        .then((response) => {
          if (response.events && response.events.length > 0) {
            for (const event of response.events) {
              const existing = events.find((e) => e.id === (event as GameEvent).id);
              if (!existing) {
                dispatch({ type: 'ADD_EVENT', payload: event as GameEvent });
              }
            }
          }
          setHasBackfilled(true);
        })
        .catch((err) => {
          console.error('Failed to backfill events:', err);
          setHasBackfilled(true);
        });
    }
  }, [sessionId, hasBackfilled]);

  let filteredEvents = events;
  if (filterType) {
    filteredEvents = filteredEvents.filter((e) => e.event_type === filterType);
  }
  if (filterTurn) {
    const turnNum = parseInt(filterTurn, 10);
    if (!isNaN(turnNum)) {
      filteredEvents = filteredEvents.filter((e) => e.turn_number === turnNum);
    }
  }

  const recentEvents = filteredEvents.slice(-50).reverse();

  const selectedEventData = selectedEvent
    ? events.find((e) => e.id === selectedEvent)
    : null;

  return (
    <div className={`panel event-debug-panel ${isCollapsed ? 'collapsed' : ''}`}>
      <div className="panel-header">
        <h3 className="panel-title">Events ({events.length})</h3>
        <div className="panel-actions">
          {sessionId && (
            <button
              className="replay-link-btn"
              onClick={() => navigate(`/session/${sessionId}/replay`)}
              title="Open session replay"
            >
              Replay
            </button>
          )}
          <button
            className="collapse-btn"
            onClick={() => setIsCollapsed(!isCollapsed)}
            aria-label={isCollapsed ? 'Expand' : 'Collapse'}
          >
            {isCollapsed ? '▶' : '▼'}
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <div className="event-debug-content">
          <div className="event-filters">
            <select
              className="event-filter-select"
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
            >
              <option value="">All types</option>
              {EVENT_TYPE_OPTIONS.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>

            <input
              type="number"
              className="event-filter-turn"
              placeholder="Turn #"
              value={filterTurn}
              onChange={(e) => setFilterTurn(e.target.value)}
              min={0}
            />

            {(filterType || filterTurn) && (
              <button
                className="filter-clear-btn"
                onClick={() => { setFilterType(''); setFilterTurn(''); }}
              >
                Clear
              </button>
            )}

            <span className="filter-count">
              {filteredEvents.length !== events.length
                ? `${filteredEvents.length} of ${events.length}`
                : `${events.length} total`}
            </span>
          </div>

          <div className="event-list">
            {recentEvents.length === 0 ? (
              <p className="empty-state">No events match filters.</p>
            ) : (
              recentEvents.map((event) => (
                <button
                  key={event.id}
                  className={`event-item ${selectedEvent === event.id ? 'selected' : ''}`}
                  onClick={() =>
                    setSelectedEvent(selectedEvent === event.id ? null : event.id)
                  }
                >
                  <span className={`event-type event-type-${event.event_type.replace('.', '-')}`}>
                    {event.event_type}
                  </span>
                  <span className="event-turn">T{event.turn_number}</span>
                </button>
              ))
            )}
          </div>

          {selectedEventData && (
            <div className="event-detail">
              <h4>Event Details</h4>
              <pre className="event-json">
                {JSON.stringify(selectedEventData, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
