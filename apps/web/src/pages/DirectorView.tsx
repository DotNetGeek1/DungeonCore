import { useParams, Link } from 'react-router-dom';
import SessionLayout from '../components/SessionLayout';

export default function DirectorView() {
  const { sessionId } = useParams<{ sessionId: string }>();

  return (
    <div className="session-view director-view">
      <header className="session-header">
        <Link to="/" className="back-link">← Home</Link>
        <h1>Session: {sessionId}</h1>
        <div className="view-mode-badge director">Director</div>
      </header>
      <SessionLayout sessionId={sessionId!} isDirector={true} />
    </div>
  );
}
