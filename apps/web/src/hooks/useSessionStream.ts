import { useEffect, useRef, useCallback } from 'react';
import type { SessionAction } from '../context/SessionContext';
import { api } from '../api/client';

const WS_BASE = import.meta.env.VITE_WS_URL || '';
const MAX_RECONNECT_ATTEMPTS = 2;

export function useSessionStream(
  sessionId: string,
  dispatch: React.Dispatch<SessionAction>
) {
  const wsRef = useRef<WebSocket | null>(null);
  const attemptsRef = useRef(0);

  const fetchStateViaHttp = useCallback(async () => {
    try {
      const response = await api.getState(sessionId);
      if (response.state) {
        dispatch({ type: 'SET_GAME_STATE', payload: response.state });
        dispatch({ type: 'SET_CONNECTION_STATUS', payload: 'connected' });
      }
    } catch (err) {
      console.warn('Could not fetch session state via HTTP:', err);
      dispatch({ type: 'SET_CONNECTION_STATUS', payload: 'disconnected' });
    }
  }, [sessionId, dispatch]);

  const connect = useCallback(() => {
    if (!WS_BASE) {
      fetchStateViaHttp();
      return;
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    dispatch({ type: 'SET_CONNECTION_STATUS', payload: 'connecting' });

    try {
      const ws = new WebSocket(`${WS_BASE}/sessions/${sessionId}/stream`);

      ws.onopen = () => {
        dispatch({ type: 'SET_CONNECTION_STATUS', payload: 'connected' });
        attemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const envelope = JSON.parse(event.data);
          if (envelope.event) {
            dispatch({ type: 'ADD_EVENT', payload: envelope.event });

            const evt = envelope.event;

            if (evt.event_type === 'session.started' && evt.payload?.initial_state) {
              dispatch({ type: 'SET_GAME_STATE', payload: evt.payload.initial_state });
            }

            // state.updated carries full state snapshot - use it directly
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

            // map.updated means the dungeon_map changed - refresh full state from API
            if (evt.event_type === 'map.updated') {
              fetchStateViaHttp();
            }
          }
          if (envelope.sequence_number !== undefined) {
            dispatch({ type: 'SET_SEQUENCE', payload: envelope.sequence_number });
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      ws.onclose = () => {
        dispatch({ type: 'SET_CONNECTION_STATUS', payload: 'disconnected' });
        attemptsRef.current += 1;
        if (attemptsRef.current <= MAX_RECONNECT_ATTEMPTS) {
          setTimeout(connect, 2000);
        } else {
          fetchStateViaHttp();
        }
      };

      ws.onerror = () => {
        dispatch({ type: 'SET_CONNECTION_STATUS', payload: 'error' });
      };

      wsRef.current = ws;
    } catch {
      fetchStateViaHttp();
    }
  }, [sessionId, dispatch, fetchStateViaHttp]);

  useEffect(() => {
    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return {
    reconnect: connect,
    disconnect: () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    },
  };
}
