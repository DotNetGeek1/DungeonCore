import { useRef, useEffect, useState } from 'react';
import { useSession } from '../../context/SessionContext';
import MessageBubble from '../MessageBubble';
import { api } from '../../api/client';
import type { TableMessage, GameEvent } from '../../types/generated';

function extractStreamingText(raw: string): string {
  const speechMatch = raw.match(/"speech"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)/);
  if (speechMatch) return speechMatch[1].replace(/\\n/g, '\n').replace(/\\"/g, '"');

  const textMatch = raw.match(/"text"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)/);
  if (textMatch) return textMatch[1].replace(/\\n/g, '\n').replace(/\\"/g, '"');

  if (!raw.includes('"') && raw.length > 10) return raw;

  return '';
}

export default function TranscriptPanel() {
  const { state, dispatch } = useSession();
  const { messages, events, gameState, streamingTokens, sessionId } = state;
  const scrollRef = useRef<HTMLDivElement>(null);
  const [hasBackfilled, setHasBackfilled] = useState(false);

  // Backfill events from API when session loads (events may have been emitted before we connected)
  useEffect(() => {
    if (sessionId && !hasBackfilled) {
      console.log('[TranscriptPanel] Backfilling events for session:', sessionId);
      api.getEvents(sessionId, { limit: 500 })
        .then((response) => {
          console.log('[TranscriptPanel] Received events from API:', response.events?.length || 0);
          if (response.events && response.events.length > 0) {
            const actionResolved = response.events.filter((e: any) => e.event_type === 'action.resolved');
            console.log('[TranscriptPanel] action.resolved events in API response:', actionResolved.length, actionResolved);
            for (const event of response.events) {
              dispatch({ type: 'ADD_EVENT', payload: event as GameEvent });
            }
          }
          setHasBackfilled(true);
        })
        .catch((err) => {
          console.error('Failed to backfill events for transcript:', err);
          setHasBackfilled(true);
        });
    }
  }, [sessionId, hasBackfilled, dispatch]);

  const actorName = (id: string): string => {
    if (!gameState) return id;
    const char = gameState.characters[id];
    if (char) return char.name;
    const npc = gameState.npcs[id];
    if (npc) return npc.name;
    if (id === 'dm') return 'Dungeon Master';
    return id;
  };

  const transcriptMessages = messages.filter(
    (m) => m.channel === 'in_character'
  );

  const eventMessages: TableMessage[] = events
    .filter((e) => e.event_type === 'message.created' && (e as any).payload?.message)
    .map((e) => (e as any).payload.message as TableMessage)
    .filter((m) => m.channel === 'in_character');

  const narrations = events
    .filter((e) => e.event_type === 'narration.emitted')
    .map((e) => ({
      id: e.id,
      type: 'narration' as const,
      text: (e as any).payload?.text || '',
      created_at: e.created_at,
    }));

  const diceRolls = events
    .filter((e) => e.event_type === 'dice.rolled')
    .map((e) => ({
      id: `dice-${e.id}`,
      type: 'dice' as const,
      actor_id: (e as any).payload?.actor_id || '',
      action_type: (e as any).payload?.action_type || '',
      rolls: (e as any).payload?.rolls || [],
      created_at: e.created_at,
    }));

  const actionResolutions = events
    .filter((e) => e.event_type === 'action.resolved')
    .map((e) => {
      const payload = (e as any).payload || {};
      const actionType = payload.action_type || 'action';
      let desc = payload.description || '';
      
      // Build a description if none provided
      if (!desc && actionType) {
        if (actionType === 'attack' || actionType === 'move_and_attack') {
          const hitMiss = payload.hit === true ? 'hits' : payload.hit === false ? 'misses' : '';
          const dmg = payload.damage ? ` for ${payload.damage} damage` : '';
          desc = `${actionType === 'move_and_attack' ? 'Moves and attacks' : 'Attacks'} - ${hitMiss}${dmg}`;
        } else if (actionType === 'move') {
          desc = 'Moves';
        } else if (actionType === 'defend') {
          desc = 'Takes defensive stance';
        } else if (actionType === 'inspect') {
          desc = 'Inspects surroundings';
        } else {
          desc = actionType;
        }
      }
      
      return {
        id: `resolve-${e.id}`,
        type: 'resolution' as const,
        actor_id: payload.actor_id || '',
        action_type: actionType,
        description: desc,
        hit: payload.hit,
        damage: payload.damage,
        created_at: e.created_at,
      };
    });

  const seenIds = new Set<string>();
  const dedup = (m: TableMessage): boolean => {
    if (seenIds.has(m.id)) return false;
    seenIds.add(m.id);
    return true;
  };

  const allMessages = [...transcriptMessages, ...eventMessages].filter(dedup);

  type TranscriptItem =
    | { type: 'message'; data: TableMessage; time: string }
    | { type: 'narration'; id: string; text: string; time: string }
    | { type: 'dice'; id: string; actor_id: string; action_type: string; rolls: any[]; time: string }
    | { type: 'resolution'; id: string; actor_id: string; action_type: string; description: string; hit?: boolean; damage?: number; time: string };

  const items: TranscriptItem[] = [
    ...allMessages.map((m) => ({ type: 'message' as const, data: m, time: m.created_at })),
    ...narrations.map((n) => ({ type: 'narration' as const, id: n.id, text: n.text, time: n.created_at })),
    ...diceRolls.map((d) => ({ type: 'dice' as const, id: d.id, actor_id: d.actor_id, action_type: d.action_type, rolls: d.rolls, time: d.created_at })),
    ...actionResolutions.map((r) => ({ type: 'resolution' as const, id: r.id, actor_id: r.actor_id, action_type: r.action_type, description: r.description, hit: r.hit, damage: r.damage, time: r.created_at })),
  ].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());

  const activeStreams = Object.entries(streamingTokens).filter(([, text]) => text.length > 0);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [items.length, activeStreams.length, streamingTokens]);

  return (
    <div className="panel transcript-panel">
      <h3 className="panel-title">Transcript ({items.length})</h3>
      <div className="transcript-content" ref={scrollRef}>
        {items.length === 0 && activeStreams.length === 0 && (
          <p className="empty-state">No activity yet. Click "Step 1 Turn" or "Auto-Run" to begin.</p>
        )}
        {items.map((item) => {
          if (item.type === 'message') {
            const msg = { ...item.data, sender_name: actorName(item.data.sender_id) };
            return <MessageBubble key={msg.id} message={msg} />;
          }
          if (item.type === 'narration') {
            return (
              <div key={item.id} className="narration-block" style={{ padding: '0.75rem', margin: '0.5rem 0', background: 'var(--surface-3, #2a1a3e)', borderLeft: '3px solid #bd93f9', borderRadius: '0.25rem', fontStyle: 'italic' }}>
                <div style={{ fontSize: '0.7em', color: '#bd93f9', marginBottom: '0.25rem', fontStyle: 'normal', fontWeight: 600 }}>DUNGEON MASTER</div>
                <p className="narration-text" style={{ margin: 0 }}>{item.text}</p>
              </div>
            );
          }
          if (item.type === 'dice') {
            const rollSummary = item.rolls.map((r: any) => `${r.die}=${r.value}+${r.modifier}=${r.total}`).join(', ');
            return (
              <div key={item.id} style={{ padding: '0.4rem 0.75rem', margin: '0.25rem 0', background: 'var(--surface-3, #1a2a1a)', borderLeft: '3px solid #f1fa8c', borderRadius: '0.25rem', fontSize: '0.85em', color: '#f1fa8c' }}>
                <span style={{ fontWeight: 600 }}>{actorName(item.actor_id)}</span> rolls ({item.action_type}): {rollSummary}
              </div>
            );
          }
          if (item.type === 'resolution') {
            // Only show HIT/MISS for combat actions (attack, move_and_attack, cast_spell_basic)
            const isCombatAction = ['attack', 'move_and_attack', 'cast_spell_basic'].includes(item.action_type);
            return (
              <div key={item.id} style={{ padding: '0.4rem 0.75rem', margin: '0.25rem 0', background: 'var(--surface-3, #2a2a1a)', borderLeft: '3px solid #ffb86c', borderRadius: '0.25rem', fontSize: '0.85em', color: '#ffb86c' }}>
                <span style={{ fontWeight: 600 }}>{actorName(item.actor_id)}</span>: {item.description}
                {isCombatAction && item.hit !== undefined && item.hit !== null && <span> | {item.hit ? 'HIT' : 'MISS'}</span>}
                {isCombatAction && item.damage !== undefined && item.damage !== null && item.damage > 0 && <span> | {item.damage} damage</span>}
              </div>
            );
          }
          return null;
        })}
        {activeStreams.map(([actorId, text]) => {
          const displayText = extractStreamingText(text);
          if (!displayText) return null;
          const isDm = actorId === 'dm';
          return (
            <div
              key={`streaming-${actorId}`}
              className="narration-block streaming"
              style={{
                padding: '0.75rem',
                margin: '0.5rem 0',
                background: isDm ? 'var(--surface-3, #2a1a3e)' : 'var(--surface-2, #1a1a2e)',
                borderLeft: `3px solid ${isDm ? '#bd93f9' : '#8be9fd'}`,
                borderRadius: '0.25rem',
                fontStyle: isDm ? 'italic' : 'normal',
                opacity: 0.85,
              }}
            >
              <div style={{ fontSize: '0.7em', color: isDm ? '#bd93f9' : '#8be9fd', marginBottom: '0.25rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                {isDm ? 'DUNGEON MASTER' : actorName(actorId)}
                <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: '#50fa7b', animation: 'pulse 1s infinite' }} />
              </div>
              <p style={{ margin: 0 }}>{displayText}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
