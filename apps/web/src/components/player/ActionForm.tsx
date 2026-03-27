import { useState } from 'react';
import { useSession } from '../../context/SessionContext';
import { api } from '../../api/client';
import type { ActionTypeEnum, EntityId, PlayerTurnSubmission } from '../../types/generated';

const ACTION_TYPES: { value: ActionTypeEnum; label: string }[] = [
  { value: 'attack', label: 'Attack' },
  { value: 'move', label: 'Move' },
  { value: 'move_and_attack', label: 'Move & Attack' },
  { value: 'defend', label: 'Defend' },
  { value: 'inspect', label: 'Inspect' },
  { value: 'cast_spell_basic', label: 'Cast Spell' },
];

const STANCES = ['guard', 'dodge', 'brace'];

interface ActionFormProps {
  actorId: string;
}

export default function ActionForm({ actorId }: ActionFormProps) {
  const { state } = useSession();
  const { sessionId, gameState, awaitingHuman } = state;

  const [actionType, setActionType] = useState<ActionTypeEnum>('defend');
  const [targetId, setTargetId] = useState('');
  const [stance, setStance] = useState('guard');
  const [movementPath, setMovementPath] = useState('');
  const [spellId, setSpellId] = useState('');
  const [speech, setSpeech] = useState('');
  const [tableTalk, setTableTalk] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const isMyTurn = awaitingHuman?.actor_id === actorId;
  const allowedActions = awaitingHuman?.allowed_actions ?? [];

  const targets: { id: EntityId; name: string }[] = [];
  if (gameState) {
    for (const [id, char] of Object.entries(gameState.characters)) {
      if (id !== actorId && char.alive) targets.push({ id, name: char.name });
    }
    for (const [id, npc] of Object.entries(gameState.npcs)) {
      if (npc.alive) targets.push({ id, name: npc.name });
    }
  }

  const buildAction = (): PlayerTurnSubmission['action'] => {
    switch (actionType) {
      case 'attack':
        return { type: 'attack', target_id: targetId || undefined };
      case 'move':
        return {
          type: 'move',
          movement_path: movementPath ? movementPath.split(',').map(s => s.trim()) : [],
        };
      case 'move_and_attack':
        return {
          type: 'move_and_attack',
          target_id: targetId || undefined,
          movement_path: movementPath ? movementPath.split(',').map(s => s.trim()) : [],
        };
      case 'defend':
        return { type: 'defend', extra: { stance } };
      case 'inspect':
        return { type: 'inspect', target_id: targetId || undefined };
      case 'cast_spell_basic':
        return {
          type: 'cast_spell_basic',
          spell_id: spellId || undefined,
          target_id: targetId || undefined,
        };
      default:
        return { type: 'defend', extra: { stance: 'guard' } };
    }
  };

  const handleSubmit = async () => {
    if (!sessionId || !isMyTurn) return;
    setIsSubmitting(true);
    setFeedback(null);

    const turn: PlayerTurnSubmission = {
      speech: speech || undefined,
      table_talk: tableTalk || undefined,
      action: buildAction(),
    };

    try {
      const response = await api.submitAction(sessionId, actorId, turn);
      if (response.accepted) {
        setFeedback({ type: 'success', text: 'Action submitted!' });
        setSpeech('');
        setTableTalk('');
      } else {
        setFeedback({ type: 'error', text: `Rejected: ${response.action_status}` });
      }
    } catch (err) {
      setFeedback({
        type: 'error',
        text: err instanceof Error ? err.message : 'Submission failed',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="panel action-form-panel">
      <h3>
        Your Action
        {isMyTurn && <span className="badge badge-active">Your Turn</span>}
      </h3>

      {!isMyTurn && (
        <p className="waiting-message">Waiting for your turn...</p>
      )}

      <div className="form-group">
        <label>In-Character Speech</label>
        <textarea
          value={speech}
          onChange={(e) => setSpeech(e.target.value)}
          placeholder="Say something in character..."
          rows={2}
          disabled={!isMyTurn || isSubmitting}
        />
      </div>

      <div className="form-group">
        <label>Table Talk</label>
        <input
          type="text"
          value={tableTalk}
          onChange={(e) => setTableTalk(e.target.value)}
          placeholder="Tactical suggestion to the party..."
          disabled={!isMyTurn || isSubmitting}
        />
      </div>

      <div className="form-group">
        <label>Action Type</label>
        <select
          value={actionType}
          onChange={(e) => setActionType(e.target.value as ActionTypeEnum)}
          disabled={!isMyTurn || isSubmitting}
        >
          {ACTION_TYPES.filter(
            (at) => allowedActions.length === 0 || allowedActions.includes(at.value)
          ).map((at) => (
            <option key={at.value} value={at.value}>{at.label}</option>
          ))}
        </select>
      </div>

      {(actionType === 'attack' || actionType === 'move_and_attack' || actionType === 'inspect' || actionType === 'cast_spell_basic') && (
        <div className="form-group">
          <label>Target</label>
          <select
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            disabled={!isMyTurn || isSubmitting}
          >
            <option value="">Select target...</option>
            {targets.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>
      )}

      {actionType === 'defend' && (
        <div className="form-group">
          <label>Stance</label>
          <select
            value={stance}
            onChange={(e) => setStance(e.target.value)}
            disabled={!isMyTurn || isSubmitting}
          >
            {STANCES.map((s) => (
              <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
        </div>
      )}

      {(actionType === 'move' || actionType === 'move_and_attack') && (
        <div className="form-group">
          <label>Movement Path (comma-separated node IDs)</label>
          <input
            type="text"
            value={movementPath}
            onChange={(e) => setMovementPath(e.target.value)}
            placeholder="A1, A2, A3"
            disabled={!isMyTurn || isSubmitting}
          />
        </div>
      )}

      {actionType === 'cast_spell_basic' && (
        <div className="form-group">
          <label>Spell ID</label>
          <input
            type="text"
            value={spellId}
            onChange={(e) => setSpellId(e.target.value)}
            placeholder="e.g. magic_missile"
            disabled={!isMyTurn || isSubmitting}
          />
        </div>
      )}

      <button
        className="btn-submit-action"
        onClick={handleSubmit}
        disabled={!isMyTurn || isSubmitting}
      >
        {isSubmitting ? 'Submitting...' : 'Submit Action'}
      </button>

      {feedback && (
        <div className={`form-feedback feedback-${feedback.type}`}>
          {feedback.text}
        </div>
      )}
    </div>
  );
}
