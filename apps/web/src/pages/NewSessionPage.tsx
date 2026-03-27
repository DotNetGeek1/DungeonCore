import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';

const STORY_GENRES = [
  { value: 'classic_fantasy', label: 'Classic Fantasy', description: 'Traditional sword and sorcery adventures' },
  { value: 'dark_fantasy', label: 'Dark Fantasy', description: 'Grim, morally complex tales' },
  { value: 'horror', label: 'Horror', description: 'Dread and supernatural terror' },
  { value: 'mystery', label: 'Mystery', description: 'Intrigue, clues, and investigation' },
  { value: 'heroic', label: 'Heroic', description: 'Epic battles and legendary deeds' },
  { value: 'survival', label: 'Survival', description: 'Resource management and harsh conditions' },
];

const STORY_THEMES = [
  { value: 'exploration', label: 'Exploration' },
  { value: 'combat', label: 'Combat' },
  { value: 'mystery', label: 'Mystery' },
  { value: 'social', label: 'Social Intrigue' },
  { value: 'puzzle', label: 'Puzzles' },
  { value: 'stealth', label: 'Stealth' },
  { value: 'treasure', label: 'Treasure Hunting' },
  { value: 'rescue', label: 'Rescue Mission' },
];

const MAP_COMPLEXITIES = [
  { value: 'simple', label: 'Simple', description: '3-5 rooms, straightforward layout' },
  { value: 'medium', label: 'Medium', description: '5-8 rooms, branching paths' },
  { value: 'complex', label: 'Complex', description: '8-12 rooms, multiple routes and secrets' },
];

export default function NewSessionPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [sessionType, setSessionType] = useState<'quick' | 'custom'>('quick');
  const [generateDynamicMap, setGenerateDynamicMap] = useState(true);
  const [storyGenre, setStoryGenre] = useState('classic_fantasy');
  const [selectedThemes, setSelectedThemes] = useState<string[]>(['exploration', 'combat']);
  const [mapComplexity, setMapComplexity] = useState('medium');

  function toggleTheme(theme: string) {
    setSelectedThemes((prev) =>
      prev.includes(theme) ? prev.filter((t) => t !== theme) : [...prev, theme]
    );
  }

  async function handleStartQuick() {
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
  }

  async function handleStartCustom() {
    setLoading(true);
    setError(null);
    try {
      const response = await api.startSession({
        campaign_id: 'mvp-campaign',
        scene_id: 'mvp-scene',
        use_mvp_scenario: true,
        generate_dynamic_map: generateDynamicMap,
        story_genre: storyGenre,
        story_themes: selectedThemes,
        map_complexity: mapComplexity,
      });
      if (response.state?.session_id) {
        navigate(`/session/${response.state.session_id}`);
      } else {
        setError('No session_id returned from server');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to start session');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell new-session-page">
      <header className="new-session-header">
        <Link to="/" className="back-link">&larr; Home</Link>
        <h1>New Adventure</h1>
        <p className="lede">Configure your adventure or jump straight into action.</p>
      </header>

      {error && (
        <div className="new-session-error">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="dismiss-btn">&times;</button>
        </div>
      )}

      <div className="session-type-selector">
        <button
          className={`type-option ${sessionType === 'quick' ? 'active' : ''}`}
          onClick={() => setSessionType('quick')}
        >
          <h3>Quick Start</h3>
          <p>Jump into the Goblin Ambush scenario with default settings</p>
        </button>
        <button
          className={`type-option ${sessionType === 'custom' ? 'active' : ''}`}
          onClick={() => setSessionType('custom')}
        >
          <h3>Custom Adventure</h3>
          <p>Configure story genre, themes, and map complexity</p>
        </button>
      </div>

      {sessionType === 'quick' ? (
        <section className="quick-start-section panel">
          <h2>The Goblin Ambush</h2>
          <p>A classic introductory scenario featuring two heroes facing off against goblin raiders.</p>
          <ul>
            <li><strong>Theron Ironblade</strong> &mdash; Fighter, protects allies</li>
            <li><strong>Lyra Shadowstep</strong> &mdash; Rogue, flanks and scouts</li>
            <li>vs. 2 Goblin Warriors + Skrix the Shaman</li>
          </ul>
          <button onClick={handleStartQuick} disabled={loading} className="btn btn-primary btn-large">
            {loading ? 'Starting...' : 'Start Adventure'}
          </button>
        </section>
      ) : (
        <section className="custom-session-section">
          <div className="config-panel panel">
            <h2>Story Configuration</h2>

            <div className="config-group">
              <label className="config-label">Genre</label>
              <div className="genre-grid">
                {STORY_GENRES.map((genre) => (
                  <button
                    key={genre.value}
                    className={`genre-option ${storyGenre === genre.value ? 'selected' : ''}`}
                    onClick={() => setStoryGenre(genre.value)}
                  >
                    <strong>{genre.label}</strong>
                    <span>{genre.description}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="config-group">
              <label className="config-label">Themes (select multiple)</label>
              <div className="themes-grid">
                {STORY_THEMES.map((theme) => (
                  <button
                    key={theme.value}
                    className={`theme-chip ${selectedThemes.includes(theme.value) ? 'selected' : ''}`}
                    onClick={() => toggleTheme(theme.value)}
                  >
                    {theme.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="config-panel panel">
            <h2>Map Configuration</h2>

            <div className="config-group">
              <div className="toggle-row">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={generateDynamicMap}
                    onChange={(e) => setGenerateDynamicMap(e.target.checked)}
                  />
                  <span className="toggle-text">Generate Dynamic Map</span>
                </label>
                <span className="toggle-hint">AI creates a unique map for each session</span>
              </div>
            </div>

            {generateDynamicMap && (
              <div className="config-group">
                <label className="config-label">Map Complexity</label>
                <div className="complexity-options">
                  {MAP_COMPLEXITIES.map((complexity) => (
                    <button
                      key={complexity.value}
                      className={`complexity-option ${mapComplexity === complexity.value ? 'selected' : ''}`}
                      onClick={() => setMapComplexity(complexity.value)}
                    >
                      <strong>{complexity.label}</strong>
                      <span>{complexity.description}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="custom-start-actions">
            <button onClick={handleStartCustom} disabled={loading} className="btn btn-primary btn-large">
              {loading ? 'Creating Adventure...' : 'Start Custom Adventure'}
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
