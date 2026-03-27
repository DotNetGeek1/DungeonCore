import { useState } from 'react';
import { useSession } from '../../context/SessionContext';
import { api } from '../../api/client';

interface EditablePatch {
  target_id: string;
  field: string;
  value: string;
}

export default function StateEditor() {
  const { state } = useSession();
  const { sessionId, gameState } = state;

  const [patches, setPatches] = useState<EditablePatch[]>([
    { target_id: '', field: 'hp', value: '' },
  ]);
  const [reason, setReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const allEntities: { id: string; name: string; hp: number }[] = [];
  if (gameState) {
    for (const [id, char] of Object.entries(gameState.characters)) {
      allEntities.push({ id, name: char.name, hp: char.hp });
    }
    for (const [id, npc] of Object.entries(gameState.npcs)) {
      allEntities.push({ id, name: npc.name, hp: npc.hp });
    }
  }

  const EDITABLE_FIELDS = ['hp', 'alive', 'status_effects'];

  const updatePatch = (index: number, field: keyof EditablePatch, value: string) => {
    const updated = [...patches];
    updated[index] = { ...updated[index], [field]: value };
    setPatches(updated);
  };

  const addPatch = () => {
    setPatches([...patches, { target_id: '', field: 'hp', value: '' }]);
  };

  const removePatch = (index: number) => {
    setPatches(patches.filter((_, i) => i !== index));
  };

  const parseValue = (field: string, raw: string): unknown => {
    if (field === 'hp') return parseInt(raw, 10) || 0;
    if (field === 'alive') return raw.toLowerCase() === 'true';
    if (field === 'status_effects') {
      return raw ? raw.split(',').map((s) => s.trim()) : [];
    }
    return raw;
  };

  const handleSubmit = async () => {
    if (!sessionId) return;
    setIsSubmitting(true);
    setFeedback(null);

    const validPatches = patches
      .filter((p) => p.target_id && p.field && p.value !== '')
      .map((p) => ({
        target_id: p.target_id,
        field: p.field,
        value: parseValue(p.field, p.value),
      }));

    if (validPatches.length === 0) {
      setFeedback({ type: 'error', text: 'No valid patches to apply' });
      setIsSubmitting(false);
      return;
    }

    try {
      const response = await api.editState(sessionId, validPatches, reason || undefined);
      setFeedback({
        type: response.accepted ? 'success' : 'error',
        text: response.message || `Applied ${response.patches_applied} patches`,
      });
    } catch (err) {
      setFeedback({
        type: 'error',
        text: err instanceof Error ? err.message : 'Edit failed',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="panel state-editor-panel">
      <h3>State Editor</h3>
      <p className="panel-hint">Directly edit entity state (dev mode).</p>

      {patches.map((patch, idx) => (
        <div key={idx} className="patch-row">
          <select
            value={patch.target_id}
            onChange={(e) => updatePatch(idx, 'target_id', e.target.value)}
          >
            <option value="">Entity...</option>
            {allEntities.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name} (HP: {e.hp})
              </option>
            ))}
          </select>

          <select
            value={patch.field}
            onChange={(e) => updatePatch(idx, 'field', e.target.value)}
          >
            {EDITABLE_FIELDS.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>

          <input
            type="text"
            value={patch.value}
            onChange={(e) => updatePatch(idx, 'value', e.target.value)}
            placeholder={patch.field === 'alive' ? 'true/false' : 'value'}
          />

          <button
            className="btn-remove-patch"
            onClick={() => removePatch(idx)}
            disabled={patches.length <= 1}
          >
            ×
          </button>
        </div>
      ))}

      <button className="btn-add-patch" onClick={addPatch}>+ Add Patch</button>

      <div className="form-group">
        <label>Reason</label>
        <input
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why edit state?"
        />
      </div>

      <button
        className="toolbar-btn btn-apply-edits"
        onClick={handleSubmit}
        disabled={isSubmitting}
      >
        {isSubmitting ? 'Applying...' : 'Apply Edits'}
      </button>

      {feedback && (
        <div className={`form-feedback feedback-${feedback.type}`}>{feedback.text}</div>
      )}
    </div>
  );
}
