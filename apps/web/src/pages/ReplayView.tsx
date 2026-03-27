import { useParams, Link } from 'react-router-dom';
import { useState, useEffect, useRef, useCallback, useReducer } from 'react';
import { api } from '../api/client';
import type { GameState, GameEvent, TableMessage, ReplayData } from '../types/generated';

interface ReplayState {
  initialState: GameState | null;
  currentState: GameState | null;
  events: GameEvent[];
  messages: TableMessage[];
  currentIndex: number;
  isPlaying: boolean;
  speed: number;
  isLoading: boolean;
  error: string | null;
}

type ReplayAction =
  | { type: 'LOAD_DATA'; payload: ReplayData }
  | { type: 'LOAD_ERROR'; payload: string }
  | { type: 'STEP_FORWARD' }
  | { type: 'STEP_BACK' }
  | { type: 'SEEK'; payload: number }
  | { type: 'TOGGLE_PLAY' }
  | { type: 'SET_SPEED'; payload: number }
  | { type: 'STOP' };

function applyEvent(state: GameState | null, event: GameEvent): { state: GameState | null; message: TableMessage | null } {
  if (!state) return { state, message: null };

  let message: TableMessage | null = null;

  switch (event.event_type) {
    case 'session.started':
      return { state: event.payload.initial_state as GameState, message: null };

    case 'state.updated':
      return { state: { ...state, ...event.payload.patch } as GameState, message: null };

    case 'message.created':
      return { state, message: event.payload.message };

    case 'discussion.opened':
    case 'discussion.closed':
      return {
        state: {
          ...state,
          turn: {
            ...state.turn,
            discussion_open: event.event_type === 'discussion.opened',
          },
        } as GameState,
        message: null,
      };

    case 'scene.started':
      return {
        state: {
          ...state,
          scene: {
            ...state.scene,
            phase: event.payload.phase,
          },
        } as GameState,
        message: null,
      };

    case 'turn.ended':
      return {
        state: {
          ...state,
          turn: {
            ...state.turn,
            turn_number: event.payload.turn_number + 1,
            phase: event.payload.next_phase,
            active_actor_id: event.payload.next_active_actor_id,
          },
          scene: {
            ...state.scene,
            phase: event.payload.next_phase,
            turn_number: event.payload.turn_number + 1,
            active_actor_id: event.payload.next_active_actor_id,
          },
        } as GameState,
        message: null,
      };

    default:
      return { state, message: null };
  }
}

const initialReplayState: ReplayState = {
  initialState: null,
  currentState: null,
  events: [],
  messages: [],
  currentIndex: -1,
  isPlaying: false,
  speed: 1,
  isLoading: true,
  error: null,
};

function replayReducer(state: ReplayState, action: ReplayAction): ReplayState {
  switch (action.type) {
    case 'LOAD_DATA': {
      const initial = action.payload.initial_state as GameState | null;
      return {
        ...state,
        initialState: initial,
        currentState: initial,
        events: action.payload.events as GameEvent[],
        messages: [],
        currentIndex: -1,
        isLoading: false,
      };
    }
    case 'LOAD_ERROR':
      return { ...state, isLoading: false, error: action.payload };

    case 'STEP_FORWARD': {
      const nextIdx = state.currentIndex + 1;
      if (nextIdx >= state.events.length) {
        return { ...state, isPlaying: false };
      }
      const event = state.events[nextIdx];
      const { state: newState, message } = applyEvent(state.currentState, event);
      const newMessages = message ? [...state.messages, message] : state.messages;
      return { ...state, currentIndex: nextIdx, currentState: newState, messages: newMessages };
    }

    case 'STEP_BACK': {
      if (state.currentIndex <= -1) return state;
      let rebuiltState = state.initialState;
      const rebuiltMessages: TableMessage[] = [];
      const targetIdx = state.currentIndex - 1;
      for (let i = 0; i <= targetIdx; i++) {
        const { state: s, message } = applyEvent(rebuiltState, state.events[i]);
        rebuiltState = s;
        if (message) rebuiltMessages.push(message);
      }
      return { ...state, currentIndex: targetIdx, currentState: rebuiltState, messages: rebuiltMessages };
    }

    case 'SEEK': {
      let rebuiltState = state.initialState;
      const rebuiltMessages: TableMessage[] = [];
      for (let i = 0; i <= action.payload; i++) {
        const { state: s, message } = applyEvent(rebuiltState, state.events[i]);
        rebuiltState = s;
        if (message) rebuiltMessages.push(message);
      }
      return { ...state, currentIndex: action.payload, currentState: rebuiltState, messages: rebuiltMessages };
    }

    case 'TOGGLE_PLAY':
      return { ...state, isPlaying: !state.isPlaying };
    case 'SET_SPEED':
      return { ...state, speed: action.payload };
    case 'STOP':
      return { ...state, isPlaying: false };
    default:
      return state;
  }
}

const SPEED_OPTIONS = [0.5, 1, 2, 4];

export default function ReplayView() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [state, dispatch] = useReducer(replayReducer, initialReplayState);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!sessionId) return;

    api.getReplayData(sessionId)
      .then((data) => dispatch({ type: 'LOAD_DATA', payload: data }))
      .catch((err) => dispatch({ type: 'LOAD_ERROR', payload: err.message }));
  }, [sessionId]);

  useEffect(() => {
    if (state.isPlaying) {
      timerRef.current = setInterval(() => {
        dispatch({ type: 'STEP_FORWARD' });
      }, 1000 / state.speed);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [state.isPlaying, state.speed]);

  useEffect(() => {
    if (state.currentIndex >= state.events.length - 1 && state.isPlaying) {
      dispatch({ type: 'STOP' });
    }
  }, [state.currentIndex, state.events.length, state.isPlaying]);

  const currentEvent = state.currentIndex >= 0 ? state.events[state.currentIndex] : null;
  const progress = state.events.length > 0
    ? ((state.currentIndex + 1) / state.events.length) * 100
    : 0;

  if (state.isLoading) {
    return (
      <div className="session-view replay-view">
        <header className="session-header">
          <Link to="/" className="back-link">← Home</Link>
          <h1>Loading Replay...</h1>
        </header>
      </div>
    );
  }

  if (state.error) {
    return (
      <div className="session-view replay-view">
        <header className="session-header">
          <Link to="/" className="back-link">← Home</Link>
          <h1>Replay Error</h1>
        </header>
        <main className="placeholder-content">
          <div className="panel"><p>{state.error}</p></div>
        </main>
      </div>
    );
  }

  return (
    <div className="session-view replay-view">
      <header className="session-header">
        <Link to="/" className="back-link">← Home</Link>
        <h1>Replay: {sessionId?.slice(0, 8)}...</h1>
        <div className="view-mode-badge replay">Replay</div>
      </header>

      <div className="session-layout">
        <div className="replay-controls">
          <div className="replay-buttons">
            <button
              className="replay-btn"
              onClick={() => dispatch({ type: 'STEP_BACK' })}
              disabled={state.currentIndex <= -1}
            >
              ◀ Step Back
            </button>

            <button
              className="replay-btn replay-btn-primary"
              onClick={() => dispatch({ type: 'TOGGLE_PLAY' })}
            >
              {state.isPlaying ? '⏸ Pause' : '▶ Play'}
            </button>

            <button
              className="replay-btn"
              onClick={() => dispatch({ type: 'STEP_FORWARD' })}
              disabled={state.currentIndex >= state.events.length - 1}
            >
              Step Forward ▶
            </button>
          </div>

          <div className="replay-speed">
            <span>Speed:</span>
            {SPEED_OPTIONS.map((s) => (
              <button
                key={s}
                className={`speed-btn ${state.speed === s ? 'active' : ''}`}
                onClick={() => dispatch({ type: 'SET_SPEED', payload: s })}
              >
                {s}x
              </button>
            ))}
          </div>

          <div className="replay-progress">
            <input
              type="range"
              min={-1}
              max={state.events.length - 1}
              value={state.currentIndex}
              onChange={(e) => dispatch({ type: 'SEEK', payload: parseInt(e.target.value) })}
              className="replay-scrubber"
            />
            <span className="replay-counter">
              {state.currentIndex + 1} / {state.events.length} events
            </span>
          </div>
        </div>

        <main className="session-main-grid">
        <div className="session-left-column">
          <div className="panel">
            <h3>Transcript</h3>
            <div className="transcript-content">
              {state.messages.length === 0 ? (
                <p className="empty-state">No messages yet.</p>
              ) : (
                state.messages.map((msg, i) => (
                  <div key={i} className={`message-bubble channel-${msg.channel}`}>
                    <span className="message-sender">{msg.sender_id}</span>
                    <span className="message-text">{msg.text}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="panel">
            <h3>Current Event</h3>
            {currentEvent ? (
              <div className="event-detail">
                <span className={`event-type event-type-${currentEvent.event_type.replace('.', '-')}`}>
                  {currentEvent.event_type}
                </span>
                <span className="event-turn">Turn {currentEvent.turn_number}</span>
                <pre className="event-json">{JSON.stringify(currentEvent.payload, null, 2)}</pre>
              </div>
            ) : (
              <p className="empty-state">No event selected. Press Play or Step Forward.</p>
            )}
          </div>
        </div>

        <div className="session-right-column">
          <div className="panel">
            <h3>Game State</h3>
            {state.currentState ? (
              <div className="state-display">
                <div className="state-section">
                  <h4>Scene: {state.currentState.scene?.name}</h4>
                  <p>Phase: {state.currentState.scene?.phase}</p>
                  <p>Turn: {state.currentState.turn?.turn_number}</p>
                  <p>Active: {state.currentState.turn?.active_actor_id || 'none'}</p>
                </div>
                <div className="state-section">
                  <h4>Characters</h4>
                  {Object.values(state.currentState.characters || {}).map((char) => (
                    <div key={char.actor_id} className="actor-mini">
                      <strong>{char.name}</strong>: {char.hp}/{char.max_hp} HP, AC {char.ac}
                      {!char.alive && <span className="dead-badge"> DEAD</span>}
                    </div>
                  ))}
                </div>
                <div className="state-section">
                  <h4>NPCs</h4>
                  {Object.values(state.currentState.npcs || {}).map((npc) => (
                    <div key={npc.actor_id} className="actor-mini">
                      <strong>{npc.name}</strong>: {npc.hp}/{npc.max_hp} HP, AC {npc.ac}
                      {!npc.alive && <span className="dead-badge"> DEAD</span>}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="empty-state">No state loaded.</p>
            )}
          </div>

          <div className="panel">
            <h3>Event Timeline</h3>
            <div className="event-timeline">
              {state.events.map((event, i) => (
                <button
                  key={event.id}
                  className={`timeline-event ${i === state.currentIndex ? 'active' : ''} ${i < state.currentIndex ? 'past' : ''}`}
                  onClick={() => dispatch({ type: 'SEEK', payload: i })}
                >
                  <span className="timeline-index">{i + 1}</span>
                  <span className={`event-type event-type-${event.event_type.replace('.', '-')}`}>
                    {event.event_type}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
        </main>
      </div>
    </div>
  );
}
