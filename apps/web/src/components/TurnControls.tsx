import { useState, useRef, useCallback } from 'react';
import { useSession } from '../context/SessionContext';
import { api } from '../api/client';

export default function TurnControls() {
  const { state, dispatch } = useSession();
  const { sessionId } = state;
  const [running, setRunning] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const turnCountRef = useRef(0);

  const tokenBufferRef = useRef('');

  const processSSEEvent = useCallback((evt: any) => {
    if (evt.event_type === 'agent.token') {
      const token = evt.payload?.token || '';
      const actorId = evt.payload?.actor_id || 'dm';
      tokenBufferRef.current += token;
      dispatch({ type: 'APPEND_STREAMING_TOKEN', payload: { actorId, token } });
      setStatus(`Generating: ${tokenBufferRef.current.slice(-60).replace(/\n/g, ' ')}`);
      return;
    }

    if (tokenBufferRef.current) {
      tokenBufferRef.current = '';
      dispatch({ type: 'CLEAR_STREAMING_TOKENS' });
    }

    dispatch({ type: 'ADD_EVENT', payload: evt });

    if (evt.event_type === 'message.created' && evt.payload?.message) {
      dispatch({ type: 'ADD_MESSAGE', payload: evt.payload.message });
    }

    if (evt.event_type === 'state.updated' && evt.payload?.state) {
      dispatch({ type: 'SET_GAME_STATE', payload: evt.payload.state });
    }

    if (evt.event_type === 'action.resolved' && evt.payload?.state_patches?.length) {
      dispatch({ type: 'APPLY_STATE_PATCHES', payload: evt.payload.state_patches });
    }

    const et = evt.event_type || '';
    if (et === 'scene.started') setStatus('Scene starting...');
    else if (et === 'narration.emitted') setStatus('DM narrating...');
    else if (et.includes('discussion.opened')) setStatus('Discussion phase...');
    else if (et === 'message.created') setStatus('Agents talking...');
    else if (et === 'action.proposed') setStatus('Action proposed...');
    else if (et === 'action.resolved') setStatus('Resolving action...');
    else if (et === 'dice.rolled') setStatus('Rolling dice...');
    else if (et === 'turn.ended') setStatus('Turn ending...');
  }, [dispatch]);

  const handleStreamTurn = useCallback(() => {
    if (!sessionId) return;
    setRunning(true);
    setError(null);
    setStatus('Agents thinking...');

    const es = new EventSource(api.streamTurnUrl(sessionId));
    eventSourceRef.current = es;

    es.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data);
        if (evt.event_type === 'turn.started') {
          setStatus(`Turn ${evt.payload?.turn_number || '?'} - agents thinking...`);
          return;
        }
        if (evt.event_type === 'turn.complete') {
          if (evt.payload?.state) dispatch({ type: 'SET_GAME_STATE', payload: evt.payload.state });
          setStatus('Turn complete');
          es.close();
          eventSourceRef.current = null;
          setRunning(false);
          return;
        }
        if (evt.event_type === 'error' || evt.event_type === 'timeout') {
          setError(evt.payload?.message || 'Error');
          es.close();
          eventSourceRef.current = null;
          setRunning(false);
          return;
        }
        processSSEEvent(evt);
      } catch (err) {
        console.error('SSE parse error:', err);
      }
    };

    es.onerror = () => {
      es.close();
      eventSourceRef.current = null;
      setRunning(false);
    };
  }, [sessionId, dispatch, processSSEEvent]);

  const handlePlay = useCallback(() => {
    if (!sessionId) return;
    setPlaying(true);
    setRunning(true);
    setError(null);
    turnCountRef.current = 0;
    setStatus('Starting continuous play...');

    const es = new EventSource(api.streamPlayUrl(sessionId, 20));
    eventSourceRef.current = es;

    es.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data);
        if (evt.event_type === 'play.started') {
          setStatus('Game is running...');
          return;
        }
        if (evt.event_type === 'turn.complete') {
          turnCountRef.current++;
          if (evt.payload?.state) dispatch({ type: 'SET_GAME_STATE', payload: evt.payload.state });
          setStatus(`Turn ${turnCountRef.current} complete - continuing...`);
          return;
        }
        if (evt.event_type === 'play.ended' || evt.event_type === 'timeout' || evt.event_type === 'error') {
          setStatus(`Game paused after ${turnCountRef.current} turns`);
          es.close();
          eventSourceRef.current = null;
          setPlaying(false);
          setRunning(false);
          return;
        }
        processSSEEvent(evt);
      } catch (err) {
        console.error('SSE parse error:', err);
      }
    };

    es.onerror = () => {
      es.close();
      eventSourceRef.current = null;
      setPlaying(false);
      setRunning(false);
      setStatus(`Stopped after ${turnCountRef.current} turns`);
    };
  }, [sessionId, dispatch, processSSEEvent]);

  const handleStop = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setPlaying(false);
    setRunning(false);
    setStatus(`Stopped after ${turnCountRef.current} turns`);
  };

  return (
    <div className="turn-controls-inline">
      {!playing ? (
        <>
          <button onClick={handlePlay} disabled={running} className="btn-control btn-play">
            &#9654; Play
          </button>
          <button onClick={handleStreamTurn} disabled={running} className="btn-control btn-step">
            Step 1 Turn
          </button>
        </>
      ) : (
        <button onClick={handleStop} className="btn-control btn-stop">
          &#9632; Stop
        </button>
      )}
      {status && !error && (
        <span className="turn-status">
          {running && <span className="turn-status-dot">&#9679;</span>}
          {status}
        </span>
      )}
      {error && <span className="turn-error">{error}</span>}
    </div>
  );
}
