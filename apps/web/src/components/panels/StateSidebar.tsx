import { useSession } from '../../context/SessionContext';
import ActorCard from '../ActorCard';

export default function StateSidebar() {
  const { state } = useSession();
  const { gameState } = state;

  const characters = gameState?.characters ? Object.values(gameState.characters) : [];
  const npcs = gameState?.npcs ? Object.values(gameState.npcs) : [];
  const objectives = gameState?.objectives ?? [];
  const flags = gameState?.flags ?? {};

  return (
    <div className="panel state-sidebar">
      <h3 className="panel-title">Game State</h3>

      <section className="state-section">
        <h4 className="section-title">Characters ({characters.length})</h4>
        <div className="actor-list">
          {characters.length === 0 ? (
            <p className="empty-state">No characters</p>
          ) : (
            characters.map((char) => (
              <ActorCard
                key={char.actor_id}
                actor={char}
                isActive={char.actor_id === gameState?.scene.active_actor_id}
              />
            ))
          )}
        </div>
      </section>

      <section className="state-section">
        <h4 className="section-title">NPCs ({npcs.length})</h4>
        <div className="actor-list">
          {npcs.length === 0 ? (
            <p className="empty-state">No NPCs</p>
          ) : (
            npcs.map((npc) => (
              <ActorCard
                key={npc.actor_id}
                actor={npc}
                isActive={npc.actor_id === gameState?.scene.active_actor_id}
              />
            ))
          )}
        </div>
      </section>

      {objectives.length > 0 && (
        <section className="state-section">
          <h4 className="section-title">Objectives</h4>
          <ul className="objective-list">
            {objectives.map((obj) => (
              <li
                key={obj.objective_id}
                className={`objective-item objective-${obj.status}`}
              >
                <span className="objective-status">{obj.status}</span>
                <span className="objective-label">{obj.label}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {Object.keys(flags).length > 0 && (
        <section className="state-section">
          <h4 className="section-title">Flags</h4>
          <div className="flags-list">
            {Object.entries(flags).map(([key, value]) => (
              <div key={key} className="flag-item">
                <span className="flag-key">{key}</span>
                <span className="flag-value">{String(value)}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
