import { Routes, Route } from 'react-router-dom';
import Landing from './pages/Landing';
import SpectatorView from './pages/SpectatorView';
import DirectorView from './pages/DirectorView';
import PlayerView from './pages/PlayerView';
import ReplayView from './pages/ReplayView';
import SessionsPage from './pages/SessionsPage';
import SessionHistoryPage from './pages/SessionHistoryPage';
import NewSessionPage from './pages/NewSessionPage';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/new" element={<NewSessionPage />} />
      <Route path="/sessions" element={<SessionsPage />} />
      <Route path="/session/:sessionId" element={<SpectatorView />} />
      <Route path="/session/:sessionId/director" element={<DirectorView />} />
      <Route path="/session/:sessionId/player/:actorId" element={<PlayerView />} />
      <Route path="/session/:sessionId/replay" element={<ReplayView />} />
      <Route path="/session/:sessionId/history" element={<SessionHistoryPage />} />
    </Routes>
  );
}
