import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';

const services = [
  { name: "Orchestrator", port: "8001", role: "Turn-state machine" },
  { name: "Agent Runtime", port: "8002", role: "LLM provider boundary" },
  { name: "Game Engine", port: "8003", role: "Deterministic rules" },
  { name: "Communication", port: "8004", role: "Visibility and message budgets" },
];

export default function Landing() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleStartMvp = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.startMvpSession();
      if (response.session_id) {
        navigate(`/session/${response.session_id}`);
      } else {
        setError('No session_id returned from server');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to start session');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">DungeonCore</p>
        <h1>Multi-agent D&amp;D Runtime</h1>
        <p className="lede">
          Watch AI agents play Dungeons &amp; Dragons. Start the Goblin Ambush
          scenario to see two player agents coordinate against three goblins,
          narrated by an AI Dungeon Master.
        </p>
        <div className="hero-actions">
          <button
            onClick={handleStartMvp}
            disabled={loading}
            className="btn btn-primary"
          >
            {loading ? 'Starting...' : 'Quick Start'}
          </button>
          <Link to="/new" className="btn btn-secondary">
            Custom Adventure
          </Link>
          <Link to="/sessions" className="btn btn-secondary">
            View All Sessions
          </Link>
        </div>
        {error && <p className="error-text" style={{ color: '#e74c3c', marginTop: '1rem' }}>{error}</p>}
      </section>

      <section className="panel-grid">
        <article className="panel">
          <h2>The Goblin Ambush</h2>
          <ul>
            <li><strong>Theron Ironblade</strong> &mdash; Fighter, protects allies</li>
            <li><strong>Lyra Shadowstep</strong> &mdash; Rogue, flanks and scouts</li>
            <li>vs. 2 Goblin Warriors + Skrix the Shaman</li>
          </ul>
        </article>

        <article className="panel">
          <h2>Session Views</h2>
          <ul>
            <li><strong>Spectator</strong> &mdash; Watch the session unfold</li>
            <li><strong>Director</strong> &mdash; Operator controls + auto-run</li>
            <li><strong>Player</strong> &mdash; Take over a character</li>
          </ul>
        </article>
      </section>

      <section className="panel">
        <h2>Service Map</h2>
        <div className="service-list">
          {services.map((service) => (
            <div className="service-card" key={service.name}>
              <strong>{service.name}</strong>
              <span>Port {service.port}</span>
              <p>{service.role}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
