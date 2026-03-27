import type { CharacterState, NpcState } from '../types/generated';

interface ActorCardProps {
  actor: CharacterState | NpcState;
  isActive?: boolean;
}

export default function ActorCard({ actor, isActive = false }: ActorCardProps) {
  const hpPercent = actor.max_hp > 0 ? (actor.hp / actor.max_hp) * 100 : 0;
  const hpClass =
    hpPercent > 50 ? 'hp-healthy' : hpPercent > 25 ? 'hp-wounded' : 'hp-critical';

  return (
    <div className={`actor-card ${isActive ? 'active' : ''} ${!actor.alive ? 'dead' : ''}`}>
      <div className="actor-header">
        <span className="actor-name">{actor.name}</span>
        <span className={`actor-role role-${actor.role}`}>{actor.role}</span>
      </div>

      <div className="actor-stats">
        <div className={`stat-hp ${hpClass}`}>
          <span className="stat-label">HP</span>
          <span className="stat-value">
            {actor.hp}/{actor.max_hp}
          </span>
          <div className="hp-bar">
            <div className="hp-fill" style={{ width: `${hpPercent}%` }} />
          </div>
        </div>

        <div className="stat-row">
          <div className="stat-item">
            <span className="stat-label">AC</span>
            <span className="stat-value">{actor.ac}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Init</span>
            <span className="stat-value">{actor.initiative}</span>
          </div>
        </div>
      </div>

      {actor.status_effects.length > 0 && (
        <div className="actor-effects">
          {actor.status_effects.map((effect, i) => (
            <span key={i} className="effect-tag">
              {effect}
            </span>
          ))}
        </div>
      )}

      {!actor.alive && <div className="dead-overlay">DEAD</div>}
    </div>
  );
}
