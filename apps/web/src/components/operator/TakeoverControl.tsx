import { useState } from 'react';
import { useSession } from '../../context/SessionContext';
import { api } from '../../api/client';

export default function TakeoverControl() {
  const { state } = useSession();
  const { sessionId, gameState } = state;
  const [selectedActor, setSelectedActor] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(
    null
  );

  const characters = gameState?.characters ? Object.values(gameState.characters) : [];
  const humanControlled = characters.filter((c) => c.controller === 'human');

  const handleTakeover = async () => {
    if (!sessionId || !selectedActor) return;

    setIsLoading(true);
    setStatus(null);

    try {
      const response = await api.takeover(sessionId, selectedActor);
      if (response.accepted) {
        setStatus({ type: 'success', message: `Takeover: ${selectedActor} → human` });
      } else {
        setStatus({ type: 'error', message: response.message || 'Takeover rejected' });
      }
    } catch (err) {
      setStatus({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to takeover',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleRelease = async (actorId: string) => {
    if (!sessionId) return;

    setIsLoading(true);
    setStatus(null);

    try {
      const response = await api.releaseTakeover(sessionId, actorId);
      if (response.accepted) {
        setStatus({ type: 'success', message: `Released: ${actorId} → agent` });
      } else {
        setStatus({ type: 'error', message: response.message || 'Release rejected' });
      }
    } catch (err) {
      setStatus({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to release',
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="takeover-control">
      <select
        className="takeover-select"
        value={selectedActor}
        onChange={(e) => setSelectedActor(e.target.value)}
        disabled={isLoading || characters.length === 0}
      >
        <option value="">Select character...</option>
        {characters.map((char) => (
          <option key={char.actor_id} value={char.actor_id}>
            {char.name} {char.controller === 'human' ? '(human)' : '(agent)'}
          </option>
        ))}
      </select>

      <button
        className="toolbar-btn btn-takeover"
        onClick={handleTakeover}
        disabled={!selectedActor || isLoading}
      >
        {isLoading ? 'Working...' : 'Takeover'}
      </button>

      {humanControlled.length > 0 && (
        <div className="release-controls">
          {humanControlled.map((char) => (
            <button
              key={char.actor_id}
              className="toolbar-btn btn-release"
              onClick={() => handleRelease(char.actor_id)}
              disabled={isLoading}
            >
              Release {char.name}
            </button>
          ))}
        </div>
      )}

      {status && (
        <span className={`takeover-status status-${status.type}`}>
          {status.message}
        </span>
      )}
    </div>
  );
}
