import { SessionProvider } from '../context/SessionContext';
import TurnInfoPanel from './panels/TurnInfoPanel';
import TranscriptPanel from './panels/TranscriptPanel';
import StateSidebar from './panels/StateSidebar';
import TacticalChatPanel from './panels/TacticalChatPanel';
import EventDebugPanel from './panels/EventDebugPanel';
import MapPanel from './panels/MapPanel';
import OperatorToolbar from './operator/OperatorToolbar';
import TurnControls from './TurnControls';

interface SessionLayoutProps {
  sessionId: string;
  isDirector: boolean;
  showTurnControls?: boolean;
}

export default function SessionLayout({ sessionId, isDirector, showTurnControls }: SessionLayoutProps) {
  return (
    <SessionProvider sessionId={sessionId}>
      <div className="session-layout">
        <div className="session-unified-header">
          <TurnInfoPanel />
          {isDirector && <OperatorToolbar />}
          {showTurnControls && !isDirector && <TurnControls />}
        </div>
        <div className="session-main-grid">
          <div className="session-left-column">
            <MapPanel isDirector={isDirector} />
            <StateSidebar />
          </div>
          <div className="session-right-column">
            <TranscriptPanel />
            <TacticalChatPanel />
            <EventDebugPanel />
          </div>
        </div>
      </div>
    </SessionProvider>
  );
}
