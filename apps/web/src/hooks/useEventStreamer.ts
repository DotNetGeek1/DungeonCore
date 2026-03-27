import { useCallback, useRef } from 'react';
import type { SessionAction } from '../context/SessionContext';

const EVENT_DELAY_MS = 150;

/**
 * Streams events into the session context one at a time with a small delay,
 * giving a real-time "chatter" feel. Also extracts message.created events
 * into the messages array for the transcript/chat panels.
 */
export function useEventStreamer(dispatch: React.Dispatch<SessionAction>) {
  const queueRef = useRef<any[]>([]);
  const streamingRef = useRef(false);

  const processQueue = useCallback(async () => {
    if (streamingRef.current) return;
    streamingRef.current = true;

    while (queueRef.current.length > 0) {
      const evt = queueRef.current.shift();
      if (!evt) continue;

      dispatch({ type: 'ADD_EVENT', payload: evt });

      if (evt.event_type === 'message.created' && evt.payload?.message) {
        dispatch({ type: 'ADD_MESSAGE', payload: evt.payload.message });
      }

      // state.updated carries a full state snapshot
      if (evt.event_type === 'state.updated' && evt.payload?.state) {
        dispatch({ type: 'SET_GAME_STATE', payload: evt.payload.state });
      }

      // turn.complete also carries full state snapshot
      if (evt.event_type === 'turn.complete' && evt.payload?.state) {
        dispatch({ type: 'SET_GAME_STATE', payload: evt.payload.state });
      }

      // action.resolved carries state patches - apply them immediately for real-time updates
      if (evt.event_type === 'action.resolved' && evt.payload?.state_patches?.length) {
        dispatch({ type: 'APPLY_STATE_PATCHES', payload: evt.payload.state_patches });
      }

      if (evt.event_type === 'action.proposed' && evt.payload?.turn) {
        const turn = evt.payload.turn;
        if (turn.speech) {
          dispatch({
            type: 'ADD_MESSAGE',
            payload: {
              id: `speech-${evt.id}`,
              turn_number: evt.turn_number,
              phase: 'action_commit',
              channel: 'in_character',
              sender_id: evt.payload.actor_id,
              sender_name: evt.payload.actor_id,
              recipient_ids: 'all',
              visibility: 'public',
              text: turn.speech,
              created_at: evt.created_at,
            },
          });
        }
        if (turn.table_talk) {
          dispatch({
            type: 'ADD_MESSAGE',
            payload: {
              id: `talk-${evt.id}`,
              turn_number: evt.turn_number,
              phase: 'action_commit',
              channel: 'table_talk',
              sender_id: evt.payload.actor_id,
              sender_name: evt.payload.actor_id,
              recipient_ids: 'all',
              visibility: 'party',
              text: turn.table_talk,
              created_at: evt.created_at,
            },
          });
        }
      }

      await new Promise((r) => setTimeout(r, EVENT_DELAY_MS));
    }

    streamingRef.current = false;
  }, [dispatch]);

  const streamEvents = useCallback(
    (events: any[]) => {
      queueRef.current.push(...events);
      processQueue();
    },
    [processQueue]
  );

  const isStreaming = useCallback(() => streamingRef.current || queueRef.current.length > 0, []);

  return { streamEvents, isStreaming };
}
