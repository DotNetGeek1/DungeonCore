import { useParams, Link } from 'react-router-dom';
import { SessionProvider } from '../context/SessionContext';
import TurnInfoPanel from '../components/panels/TurnInfoPanel';
import TranscriptPanel from '../components/panels/TranscriptPanel';
import TacticalChatPanel from '../components/panels/TacticalChatPanel';
import StateSidebar from '../components/panels/StateSidebar';
import ActionForm from '../components/player/ActionForm';
import DiscussionInput from '../components/player/DiscussionInput';

export default function PlayerView() {
  const { sessionId, actorId } = useParams<{ sessionId: string; actorId: string }>();

  if (!sessionId || !actorId) {
    return (
      <div className="session-view player-view">
        <header className="session-header">
          <Link to="/" className="back-link">← Home</Link>
          <h1>Missing Parameters</h1>
        </header>
        <main className="placeholder-content">
          <p>Session ID and Actor ID are required.</p>
        </main>
      </div>
    );
  }

  return (
    <SessionProvider sessionId={sessionId}>
      <div className="session-view player-view">
        <header className="session-header">
          <Link to="/" className="back-link">← Home</Link>
          <h1>Session: {sessionId.slice(0, 8)}...</h1>
          <div className="view-mode-badge player">Player: {actorId}</div>
        </header>

        <div className="session-layout">
          <TurnInfoPanel />

          <main className="session-main-grid">
            <div className="session-left-column">
              <TranscriptPanel />
              <TacticalChatPanel />
              <DiscussionInput actorId={actorId} />
            </div>
            <div className="session-right-column">
              <ActionForm actorId={actorId} />
              <StateSidebar />
            </div>
          </main>
        </div>
      </div>
    </SessionProvider>
  );
}
