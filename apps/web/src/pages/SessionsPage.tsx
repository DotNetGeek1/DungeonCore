import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { SessionListItem, SessionStatus } from '../types/generated';

const STATUS_LABELS: Record<SessionStatus, string> = {
  created: 'New',
  running: 'Running',
  paused: 'Paused',
  completed: 'Completed',
  error: 'Error',
};

const STATUS_CLASSES: Record<SessionStatus, string> = {
  created: 'status-created',
  running: 'status-running',
  paused: 'status-paused',
  completed: 'status-completed',
  error: 'status-error',
};

function formatDate(dateStr?: string): string {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  return date.toLocaleString();
}

export default function SessionsPage() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    loadSessions();
  }, [filter]);

  async function loadSessions() {
    setLoading(true);
    setError(null);
    try {
      const params = filter !== 'all' ? { status: filter } : undefined;
      const response = await api.listSessions(params);
      setSessions(response.sessions);
    } catch (err: any) {
      setError(err.message || 'Failed to load sessions');
    } finally {
      setLoading(false);
    }
  }

  async function handleResume(sessionId: string) {
    setActionLoading(sessionId);
    try {
      await api.resume(sessionId);
      navigate(`/session/${sessionId}`);
    } catch (err: any) {
      setError(err.message || 'Failed to resume session');
    } finally {
      setActionLoading(null);
    }
  }

  async function handlePause(sessionId: string) {
    setActionLoading(sessionId);
    try {
      await api.pause(sessionId);
      await loadSessions();
    } catch (err: any) {
      setError(err.message || 'Failed to pause session');
    } finally {
      setActionLoading(null);
    }
  }

  return (
    <main className="shell sessions-page">
      <header className="sessions-header">
        <div>
          <Link to="/" className="back-link">&larr; Home</Link>
          <h1>Sessions</h1>
          <p className="lede">View and manage your game sessions. Resume paused games or review completed adventures.</p>
        </div>
        <Link to="/new" className="btn btn-primary">New Session</Link>
      </header>

      <div className="sessions-toolbar">
        <div className="filter-group">
          <label className="filter-label">Filter:</label>
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="filter-select">
            <option value="all">All Sessions</option>
            <option value="running">Running</option>
            <option value="paused">Paused</option>
            <option value="completed">Completed</option>
            <option value="error">Error</option>
          </select>
        </div>
        <button onClick={loadSessions} className="btn btn-secondary" disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="sessions-error">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="dismiss-btn">&times;</button>
        </div>
      )}

      {loading && sessions.length === 0 ? (
        <div className="sessions-loading">
          <p>Loading sessions...</p>
        </div>
      ) : sessions.length === 0 ? (
        <div className="sessions-empty panel">
          <h2>No Sessions Found</h2>
          <p>Start a new adventure to see it here.</p>
          <Link to="/new" className="btn btn-primary">Start New Session</Link>
        </div>
      ) : (
        <div className="sessions-list">
          {sessions.map((session) => (
            <article key={session.session_id} className={`session-card panel ${STATUS_CLASSES[session.status]}`}>
              <div className="session-card-header">
                <div className="session-card-id">
                  <code>{session.session_id.slice(0, 8)}...</code>
                  <span className={`session-status-badge ${STATUS_CLASSES[session.status]}`}>
                    {STATUS_LABELS[session.status]}
                  </span>
                </div>
                <span className="session-source">{session.source === 'memory' ? 'Active' : 'Stored'}</span>
              </div>

              <div className="session-card-details">
                <div className="session-detail">
                  <span className="detail-label">Campaign</span>
                  <span className="detail-value">{session.campaign_id.slice(0, 12)}...</span>
                </div>
                <div className="session-detail">
                  <span className="detail-label">Turn</span>
                  <span className="detail-value">{session.turn_number ?? '-'}</span>
                </div>
                <div className="session-detail">
                  <span className="detail-label">Phase</span>
                  <span className="detail-value phase-value">{session.phase ?? '-'}</span>
                </div>
                {session.started_at && (
                  <div className="session-detail">
                    <span className="detail-label">Started</span>
                    <span className="detail-value">{formatDate(session.started_at)}</span>
                  </div>
                )}
                {session.paused_at && (
                  <div className="session-detail">
                    <span className="detail-label">Paused</span>
                    <span className="detail-value">{formatDate(session.paused_at)}</span>
                  </div>
                )}
              </div>

              <div className="session-card-actions">
                {session.status === 'running' && (
                  <>
                    <Link to={`/session/${session.session_id}`} className="btn btn-secondary">
                      View
                    </Link>
                    <Link to={`/session/${session.session_id}/director`} className="btn btn-secondary">
                      Director
                    </Link>
                    <button
                      onClick={() => handlePause(session.session_id)}
                      disabled={actionLoading === session.session_id}
                      className="btn btn-secondary btn-pause"
                    >
                      {actionLoading === session.session_id ? '...' : 'Pause'}
                    </button>
                  </>
                )}
                {session.status === 'paused' && (
                  <>
                    <button
                      onClick={() => handleResume(session.session_id)}
                      disabled={actionLoading === session.session_id}
                      className="btn btn-primary"
                    >
                      {actionLoading === session.session_id ? 'Resuming...' : 'Resume'}
                    </button>
                    <Link to={`/session/${session.session_id}/history`} className="btn btn-secondary">
                      History
                    </Link>
                  </>
                )}
                {(session.status === 'completed' || session.status === 'error') && (
                  <>
                    <Link to={`/session/${session.session_id}/history`} className="btn btn-secondary">
                      View History
                    </Link>
                    <Link to={`/session/${session.session_id}/replay`} className="btn btn-secondary">
                      Replay
                    </Link>
                  </>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
