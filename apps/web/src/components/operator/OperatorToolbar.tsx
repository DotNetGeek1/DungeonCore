import { useState, useRef, useCallback } from 'react';
import { useSession } from '../../context/SessionContext';
import { api } from '../../api/client';
import TakeoverControl from './TakeoverControl';
import EventInjector from './EventInjector';
import OverrideActionPanel from './OverrideActionPanel';
import StateEditor from './StateEditor';

export default function OperatorToolbar() {
  const { state, dispatch } = useSession();
  const { sessionId, isPaused, connectionStatus, gameState } = state;
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showEventInjector, setShowEventInjector] = useState(false);
  const [showStateEditor, setShowStateEditor] = useState(false);
  const [isRerunning, setIsRerunning] = useState(false);
  const [isAutoRunning, setIsAutoRunning] = useState(false);
  const [isSteppingTurn, setIsSteppingTurn] = useState(false);
  const [turnStatus, setTurnStatus] = useState('');
  
  const eventSourceRef = useRef<EventSource | null>(null);
  const tokenBufferRef = useRef('');
  const turnCountRef = useRef(0);

  const handlePause = async () => {
    if (!sessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.pause(sessionId);
      if (response.accepted) {
        dispatch({ type: 'SET_PAUSED', payload: true });
      } else {
        setError(`Pause rejected: ${response.status}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to pause');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResume = async () => {
    if (!sessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.resume(sessionId);
      if (response.accepted) {
        dispatch({ type: 'SET_PAUSED', payload: false });
      } else {
        setError(`Resume rejected: ${response.status}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resume');
    } finally {
      setIsLoading(false);
    }
  };

  const isConnected = connectionStatus === 'connected' || gameState !== null;
  const phase = gameState?.scene?.phase;
  const canRerunNarration = phase === 'narration' || phase === 'reaction' || phase === 'turn_end';

  const processSSEEvent = useCallback((evt: any) => {
    if (evt.event_type === 'agent.token') {
      const token = evt.payload?.token || '';
      const actorId = evt.payload?.actor_id || 'dm';
      tokenBufferRef.current += token;
      dispatch({ type: 'APPEND_STREAMING_TOKEN', payload: { actorId, token } });
      setTurnStatus(`Generating: ${tokenBufferRef.current.slice(-60).replace(/\n/g, ' ')}`);
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

    if (evt.event_type === 'action.resolved' && evt.payload?.state_patches?.length) {
      dispatch({ type: 'APPLY_STATE_PATCHES', payload: evt.payload.state_patches });
    }

    if (evt.event_type === 'state.updated' && evt.payload?.state) {
      dispatch({ type: 'SET_GAME_STATE', payload: evt.payload.state });
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
    }

    const et = evt.event_type || '';
    if (et === 'scene.started') setTurnStatus('Scene starting...');
    else if (et === 'narration.emitted') setTurnStatus('DM narrating...');
    else if (et.includes('discussion.opened')) setTurnStatus('Discussion phase...');
    else if (et === 'message.created') setTurnStatus('Agents talking...');
    else if (et === 'action.proposed') setTurnStatus('Action proposed...');
    else if (et === 'action.resolved') setTurnStatus('Resolving action...');
    else if (et === 'dice.rolled') setTurnStatus('Rolling dice...');
    else if (et === 'turn.ended') setTurnStatus('Turn ending...');
  }, [dispatch]);

  const handleStepTurn = useCallback(() => {
    if (!sessionId) return;
    setIsSteppingTurn(true);
    setError(null);
    setTurnStatus('Agents thinking...');

    const es = new EventSource(api.streamTurnUrl(sessionId));
    eventSourceRef.current = es;

    es.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data);
        if (evt.event_type === 'turn.started') {
          setTurnStatus(`Turn ${evt.payload?.turn_number || '?'} - agents thinking...`);
          return;
        }
        if (evt.event_type === 'turn.complete') {
          if (evt.payload?.state) dispatch({ type: 'SET_GAME_STATE', payload: evt.payload.state });
          setTurnStatus('Turn complete');
          es.close();
          eventSourceRef.current = null;
          setIsSteppingTurn(false);
          return;
        }
        if (evt.event_type === 'error' || evt.event_type === 'timeout') {
          setError(evt.payload?.message || 'Error during turn');
          es.close();
          eventSourceRef.current = null;
          setIsSteppingTurn(false);
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
      setIsSteppingTurn(false);
      setTurnStatus('Connection error');
    };
  }, [sessionId, dispatch, processSSEEvent]);

  const handleAutoRun = useCallback((turns: number) => {
    if (!sessionId) return;
    setIsAutoRunning(true);
    setError(null);
    turnCountRef.current = 0;
    setTurnStatus(`Starting ${turns} turns...`);

    const es = new EventSource(api.streamPlayUrl(sessionId, turns));
    eventSourceRef.current = es;

    es.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data);
        if (evt.event_type === 'play.started') {
          setTurnStatus('Game is running...');
          return;
        }
        if (evt.event_type === 'turn.started') {
          turnCountRef.current++;
          setTurnStatus(`Turn ${turnCountRef.current} of ${turns} - agents thinking...`);
          return;
        }
        if (evt.event_type === 'turn.complete') {
          if (evt.payload?.state) dispatch({ type: 'SET_GAME_STATE', payload: evt.payload.state });
          setTurnStatus(`Turn ${turnCountRef.current} of ${turns} complete`);
          return;
        }
        if (evt.event_type === 'play.ended' || evt.event_type === 'timeout' || evt.event_type === 'error') {
          if (evt.event_type === 'error') {
            setError(evt.payload?.message || 'Error during auto-run');
          }
          setTurnStatus(`${turnCountRef.current} turn${turnCountRef.current !== 1 ? 's' : ''} complete`);
          es.close();
          eventSourceRef.current = null;
          setIsAutoRunning(false);
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
      setIsAutoRunning(false);
      setTurnStatus(`Stopped after ${turnCountRef.current} turns`);
    };
  }, [sessionId, dispatch, processSSEEvent]);

  const handleStop = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsAutoRunning(false);
    setIsSteppingTurn(false);
    setTurnStatus(`Stopped after ${turnCountRef.current} turns`);
  }, []);

  const handleRerunNarration = async () => {
    if (!sessionId) return;
    setIsRerunning(true);
    setError(null);
    try {
      const response = await api.rerunNarration(sessionId);
      if (!response.accepted) {
        setError(response.message || 'Rerun rejected');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rerun narration');
    } finally {
      setIsRerunning(false);
    }
  };

  const busy = isAutoRunning || isSteppingTurn;

  return (
    <div className="operator-toolbar">
      <div className="toolbar-main">
        <div className="toolbar-group">
          <span className="toolbar-label">Operator Controls</span>
          
          <button
            className="toolbar-btn btn-pause"
            onClick={handlePause}
            disabled={!isConnected || isLoading || isPaused}
          >
            Pause
          </button>

          <button
            className="toolbar-btn btn-resume"
            onClick={handleResume}
            disabled={!isConnected || isLoading || !isPaused}
          >
            Resume
          </button>

          <button
            className="toolbar-btn btn-inject"
            onClick={() => setShowEventInjector(!showEventInjector)}
            disabled={!isConnected}
          >
            {showEventInjector ? 'Hide Injector' : 'Inject Event'}
          </button>

          <button
            className="toolbar-btn btn-state-editor"
            onClick={() => setShowStateEditor(!showStateEditor)}
            disabled={!isConnected}
          >
            {showStateEditor ? 'Hide Editor' : 'Edit State'}
          </button>

          <button
            className="toolbar-btn btn-rerun-narration"
            onClick={handleRerunNarration}
            disabled={!isConnected || isRerunning || !canRerunNarration}
          >
            {isRerunning ? 'Rerunning...' : 'Rerun Narration'}
          </button>
        </div>

        <div className="toolbar-group">
          <span className="toolbar-label">Turn Control</span>
          {!isAutoRunning ? (
            <>
              <button
                className="toolbar-btn btn-step"
                onClick={handleStepTurn}
                disabled={busy}
              >
                {isSteppingTurn ? 'Thinking...' : 'Step 1 Turn'}
              </button>
              <button
                className="toolbar-btn btn-autorun"
                onClick={() => handleAutoRun(3)}
                disabled={busy}
              >
                Auto-Run 3
              </button>
              <button
                className="toolbar-btn btn-autorun"
                onClick={() => handleAutoRun(5)}
                disabled={busy}
              >
                Auto-Run 5
              </button>
            </>
          ) : (
            <button
              className="toolbar-btn btn-stop"
              onClick={handleStop}
              style={{ background: '#e74c3c', color: 'white' }}
            >
              Stop
            </button>
          )}
          {turnStatus && <span className="toolbar-status">{turnStatus}</span>}
        </div>

        <div className="toolbar-group">
          <TakeoverControl />
        </div>

        {isPaused && (
          <div className="pause-indicator">
            <span className="pause-badge">PAUSED</span>
          </div>
        )}
      </div>

      {error && (
        <div className="toolbar-error">
          {error}
          <button className="dismiss-btn" onClick={() => setError(null)}>x</button>
        </div>
      )}

      {showEventInjector && (
        <EventInjector onClose={() => setShowEventInjector(false)} />
      )}

      {showStateEditor && <StateEditor />}

      <OverrideActionPanel />
    </div>
  );
}
