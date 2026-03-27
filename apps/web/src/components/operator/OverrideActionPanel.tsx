import { useState } from 'react';
import { useSession } from '../../context/SessionContext';
import { api } from '../../api/client';
import type { ActionTypeEnum, PlayerTurnSubmission } from '../../types/generated';

const ACTION_TYPES: { value: ActionTypeEnum; label: string }[] = [
  { value: 'attack', label: 'Attack' },
  { value: 'move', label: 'Move' },
  { value: 'defend', label: 'Defend' },
  { value: 'inspect', label: 'Inspect' },
  { value: 'cast_spell_basic', label: 'Cast Spell' },
];

export default function OverrideActionPanel() {
  const { state } = useSession();
  const { sessionId, gameState } = state;

  const [actionType, setActionType] = useState<ActionTypeEnum>('defend');
  const [targetId, setTargetId] = useState('');
  const [stance, setStance] = useState('guard');
  const [reason, setReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const phase = gameState?.scene?.phase;
  const canOverride = phase === 'action_commit' || phase === 'resolution';

  const targets: { id: string; name: string }[] = [];
  if (gameState) {
    for (const [id, npc] of Object.entries(gameState.npcs)) {
      if (npc.alive) targets.push({ id, name: npc.name });
    }
    for (const [id, char] of Object.entries(gameState.characters)) {
      if (char.alive) targets.push({ id, name: char.name });
    }
  }

  const handleOverride = async () => {
    if (!sessionId) return;
    setIsSubmitting(true);
    setFeedback(null);

    const action = actionType === 'defend'
      ? { type: actionType as string, extra: { stance } }
      : { type: actionType as string, target_id: targetId || undefined };

    const turn: PlayerTurnSubmission = { action };

    try {
      const response = await api.overrideAction(sessionId, turn, reason || undefined);
      setFeedback({
        type: response.accepted ? 'success' : 'error',
        text: response.message || (response.accepted ? 'Override applied' : 'Override rejected'),
      });
    } catch (err) {
      setFeedback({
        type: 'error',
        text: err instanceof Error ? err.message : 'Override failed',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!canOverride) return null;

  return (
    <div className="panel override-action-panel">
      <h3>Override Action</h3>
      <p className="panel-hint">Replace the proposed action before resolution.</p>

      <div className="form-group">
        <label>Action Type</label>
        <select value={actionType} onChange={(e) => setActionType(e.target.value as ActionTypeEnum)}>
          {ACTION_TYPES.map((at) => (
            <option key={at.value} value={at.value}>{at.label}</option>
          ))}
        </select>
      </div>

      {actionType !== 'defend' && (
        <div className="form-group">
          <label>Target</label>
          <select value={targetId} onChange={(e) => setTargetId(e.target.value)}>
            <option value="">Select target...</option>
            {targets.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>
      )}

      <div className="form-group">
        <label>Reason</label>
        <input
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why override?"
        />
      </div>

      <button
        className="toolbar-btn btn-override"
        onClick={handleOverride}
        disabled={isSubmitting}
      >
        {isSubmitting ? 'Overriding...' : 'Apply Override'}
      </button>

      {feedback && (
        <div className={`form-feedback feedback-${feedback.type}`}>{feedback.text}</div>
      )}
    </div>
  );
}
