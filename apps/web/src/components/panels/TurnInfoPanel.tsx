import { useSession } from '../../context/SessionContext';
import PhaseIndicator from '../PhaseIndicator';
import ConnectionIndicator from '../ConnectionIndicator';

export default function TurnInfoPanel() {
  const { state } = useSession();
  const { gameState, connectionStatus } = state;

  const scene = gameState?.scene;
  const turn = gameState?.turn;
  const activeActorId = scene?.active_actor_id;

  const activeActor = activeActorId
    ? gameState?.characters[activeActorId] || gameState?.npcs[activeActorId]
    : null;

  return (
    <div className="turn-info-inline">
      <ConnectionIndicator status={connectionStatus} />

      <div className="turn-info-item">
        <span className="turn-info-label">Turn</span>
        <span className="turn-info-value">{turn?.turn_number ?? 0}</span>
      </div>

      <div className="turn-info-item">
        <span className="turn-info-label">Round</span>
        <span className="turn-info-value">{turn?.round_number ?? 1}</span>
      </div>

      <div className="turn-info-item phase-item">
        <span className="turn-info-label">Phase</span>
        <PhaseIndicator phase={scene?.phase ?? 'scene_intro'} />
      </div>

      <div className="turn-info-item active-actor-item">
        <span className="turn-info-label">Active</span>
        <span className="turn-info-value actor-name">
          {activeActor?.name ?? 'None'}
        </span>
      </div>

      {turn?.discussion_open && (
        <div className="turn-info-item discussion-item">
          <span className="turn-info-label">Discussion</span>
          <span className="turn-info-value">
            {turn.remaining_discussion_messages}/{turn.max_discussion_messages}
          </span>
        </div>
      )}

      {scene && (
        <div className="scene-summary-inline">
          <strong>{scene.name}</strong>
          {scene.location_name && <span className="location"> — {scene.location_name}</span>}
        </div>
      )}
    </div>
  );
}
