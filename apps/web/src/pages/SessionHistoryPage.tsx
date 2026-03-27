import { useState, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { EventHistoryItem, SnapshotSummary } from '../types/generated';

type ViewMode = 'transcript' | 'events' | 'snapshots';

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleString();
}

function formatEventType(type: string): string {
  return type.replace(/\./g, ' ').replace(/_/g, ' ');
}

export default function SessionHistoryPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [viewMode, setViewMode] = useState<ViewMode>('transcript');
  const [transcript, setTranscript] = useState<string>('');
  const [events, setEvents] = useState<EventHistoryItem[]>([]);
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [status, setStatus] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<EventHistoryItem | null>(null);
  const [turnCount, setTurnCount] = useState(0);

  useEffect(() => {
    if (sessionId) {
      loadHistory();
    }
  }, [sessionId]);

  useEffect(() => {
    if (sessionId && viewMode === 'transcript' && !transcript) {
      loadTranscript();
    }
  }, [viewMode, sessionId, transcript]);

  async function loadHistory() {
    setLoading(true);
    setError(null);
    try {
      const response = await api.getSessionHistory(sessionId!, 500);
      setEvents(response.events);
      setSnapshots(response.snapshots);
      setStatus(response.status);
    } catch (err: any) {
      setError(err.message || 'Failed to load session history');
    } finally {
      setLoading(false);
    }
  }

  async function loadTranscript() {
    try {
      const response = await api.getSessionTranscript(sessionId!);
      setTranscript(response.transcript);
      setTurnCount(response.turn_count);
    } catch (err: any) {
      setTranscript('Failed to load transcript: ' + (err.message || 'Unknown error'));
    }
  }

  return (
    <main className="session-history-page">
      <header className="history-header">
        <div className="history-header-left">
          <Link to="/sessions" className="back-link">&larr; All Sessions</Link>
          <h1>Session History</h1>
          <p className="session-id-display">
            <code>{sessionId}</code>
            <span className={`session-status-badge status-${status.toLowerCase()}`}>{status}</span>
          </p>
        </div>
        <div className="history-header-actions">
          {status === 'PAUSED' && (
            <Link to={`/session/${sessionId}`} className="btn btn-primary">Resume Session</Link>
          )}
          <Link to={`/session/${sessionId}/replay`} className="btn btn-secondary">Replay</Link>
        </div>
      </header>

      <div className="history-tabs">
        <button
          className={`history-tab ${viewMode === 'transcript' ? 'active' : ''}`}
          onClick={() => setViewMode('transcript')}
        >
          Transcript
        </button>
        <button
          className={`history-tab ${viewMode === 'events' ? 'active' : ''}`}
          onClick={() => setViewMode('events')}
        >
          Events ({events.length})
        </button>
        <button
          className={`history-tab ${viewMode === 'snapshots' ? 'active' : ''}`}
          onClick={() => setViewMode('snapshots')}
        >
          Snapshots ({snapshots.length})
        </button>
      </div>

      {error && (
        <div className="history-error">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="dismiss-btn">&times;</button>
        </div>
      )}

      {loading ? (
        <div className="history-loading panel">
          <p>Loading session history...</p>
        </div>
      ) : (
        <div className="history-content">
          {viewMode === 'transcript' && (
            <div className="transcript-view panel">
              <div className="transcript-header">
                <h2>Adventure Transcript</h2>
                {turnCount > 0 && <span className="turn-count">{turnCount} turns</span>}
              </div>
              <div className="transcript-body">
                {transcript ? (
                  <pre className="transcript-text">{transcript}</pre>
                ) : (
                  <p className="empty-state">Loading transcript...</p>
                )}
              </div>
            </div>
          )}

          {viewMode === 'events' && (
            <div className="events-view">
              <div className="events-list-panel panel">
                <h2>Event Log</h2>
                <div className="events-list">
                  {events.length === 0 ? (
                    <p className="empty-state">No events recorded</p>
                  ) : (
                    events.map((event) => (
                      <button
                        key={event.id}
                        className={`event-item ${selectedEvent?.id === event.id ? 'selected' : ''}`}
                        onClick={() => setSelectedEvent(event)}
                      >
                        <span className="event-type">{formatEventType(event.event_type)}</span>
                        <span className="event-meta">
                          <span className="event-turn">Turn {event.turn_number}</span>
                          <span className="event-time">{formatDate(event.created_at)}</span>
                        </span>
                      </button>
                    ))
                  )}
                </div>
              </div>

              {selectedEvent && (
                <div className="event-detail-panel panel">
                  <h3>{formatEventType(selectedEvent.event_type)}</h3>
                  <div className="event-detail-meta">
                    <span>Turn {selectedEvent.turn_number}</span>
                    <span>{formatDate(selectedEvent.created_at)}</span>
                  </div>
                  <div className="event-detail">
                    <h4>Payload</h4>
                    <pre className="event-json">{JSON.stringify(selectedEvent.payload, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>
          )}

          {viewMode === 'snapshots' && (
            <div className="snapshots-view panel">
              <h2>State Snapshots</h2>
              <p className="snapshots-info">
                Snapshots are saved automatically at key moments. You can use these to review game state at specific points.
              </p>
              <div className="snapshots-list">
                {snapshots.length === 0 ? (
                  <p className="empty-state">No snapshots available</p>
                ) : (
                  <table className="snapshots-table">
                    <thead>
                      <tr>
                        <th>Snapshot ID</th>
                        <th>Turn</th>
                        <th>Phase</th>
                        <th>Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {snapshots.map((snapshot) => (
                        <tr key={snapshot.snapshot_id}>
                          <td><code>{snapshot.snapshot_id.slice(0, 8)}...</code></td>
                          <td>{snapshot.turn_number}</td>
                          <td className="phase-value">{snapshot.phase}</td>
                          <td>{formatDate(snapshot.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
