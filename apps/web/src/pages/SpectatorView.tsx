import { useParams, Link } from 'react-router-dom';
import SessionLayout from '../components/SessionLayout';

export default function SpectatorView() {
  const { sessionId } = useParams<{ sessionId: string }>();

  return (
    <div className="session-view spectator-view">
      <header className="session-header">
        <Link to="/" className="back-link">&larr; Home</Link>
        <h1>Session: {sessionId}</h1>
        <div className="view-mode-badge">Spectator</div>
      </header>
      <SessionLayout sessionId={sessionId!} isDirector={false} showTurnControls={true} />
    </div>
  );
}
