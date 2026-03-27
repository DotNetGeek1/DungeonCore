import { createContext, useContext, useReducer, useEffect, ReactNode } from 'react';
import type {
  ActionAwaitingHumanPayload,
  GameState,
  TableMessage,
  GameEvent,
  ConnectionStatus,
  TakeoverChangedPayload,
  Position,
} from '../types/generated';
import { useSessionStream } from '../hooks/useSessionStream';

interface StatePatch {
  target_id: string;
  field: string;
  old_value: unknown;
  new_value: unknown;
}

interface SessionState {
  sessionId: string | null;
  gameState: GameState | null;
  messages: TableMessage[];
  events: GameEvent[];
  connectionStatus: ConnectionStatus;
  isPaused: boolean;
  lastSequence: number;
  awaitingHuman: ActionAwaitingHumanPayload | null;
  streamingTokens: Record<string, string>;
}

type SessionAction =
  | { type: 'SET_SESSION_ID'; payload: string }
  | { type: 'SET_CONNECTION_STATUS'; payload: ConnectionStatus }
  | { type: 'SET_GAME_STATE'; payload: GameState }
  | { type: 'UPDATE_GAME_STATE'; payload: Partial<GameState> }
  | { type: 'ADD_MESSAGE'; payload: TableMessage }
  | { type: 'ADD_EVENT'; payload: GameEvent }
  | { type: 'SET_PAUSED'; payload: boolean }
  | { type: 'SET_SEQUENCE'; payload: number }
  | { type: 'SET_AWAITING_HUMAN'; payload: ActionAwaitingHumanPayload | null }
  | { type: 'TAKEOVER_CHANGED'; payload: TakeoverChangedPayload }
  | { type: 'APPLY_STATE_PATCHES'; payload: StatePatch[] }
  | { type: 'APPEND_STREAMING_TOKEN'; payload: { actorId: string; token: string } }
  | { type: 'CLEAR_STREAMING_TOKENS' }
  | { type: 'RESET' };

function parsePosition(value: unknown): Position | null {
  if (!value) return null;
  if (typeof value === 'object' && value !== null) {
    const obj = value as Record<string, unknown>;
    if (typeof obj.x === 'number' && typeof obj.y === 'number') {
      return value as Position;
    }
    if (typeof obj.node_id === 'string') {
      const parts = obj.node_id.split(',');
      if (parts.length === 2) {
        const x = parseInt(parts[0].trim(), 10);
        const y = parseInt(parts[1].trim(), 10);
        if (!isNaN(x) && !isNaN(y)) {
          return { x, y, node_id: obj.node_id };
        }
      }
    }
  }
  if (typeof value === 'string') {
    const parts = value.split(',');
    if (parts.length === 2) {
      const x = parseInt(parts[0].trim(), 10);
      const y = parseInt(parts[1].trim(), 10);
      if (!isNaN(x) && !isNaN(y)) {
        return { x, y, node_id: value };
      }
    }
  }
  return null;
}

function applyPatches(gameState: GameState, patches: StatePatch[]): GameState {
  const characters = { ...gameState.characters };
  const npcs = { ...gameState.npcs };
  const flags = { ...gameState.flags };

  for (const patch of patches) {
    const { target_id, field, new_value } = patch;

    if (target_id === 'flags') {
      if (typeof new_value === 'string' || typeof new_value === 'number' || typeof new_value === 'boolean') {
        flags[field] = new_value;
      }
      continue;
    }

    if (target_id in characters) {
      const char = characters[target_id];
      if (field === 'position') {
        const pos = parsePosition(new_value);
        if (pos) {
          characters[target_id] = { ...char, position: pos };
        }
      } else if (field === 'hp' && typeof new_value === 'number') {
        characters[target_id] = { ...char, hp: new_value };
      } else if (field === 'alive' && typeof new_value === 'boolean') {
        characters[target_id] = { ...char, alive: new_value };
      } else if (field === 'status_effects' && Array.isArray(new_value)) {
        characters[target_id] = { ...char, status_effects: new_value };
      }
    } else if (target_id in npcs) {
      const npc = npcs[target_id];
      if (field === 'position') {
        const pos = parsePosition(new_value);
        if (pos) {
          npcs[target_id] = { ...npc, position: pos };
        }
      } else if (field === 'hp' && typeof new_value === 'number') {
        npcs[target_id] = { ...npc, hp: new_value };
      } else if (field === 'alive' && typeof new_value === 'boolean') {
        npcs[target_id] = { ...npc, alive: new_value };
      } else if (field === 'status_effects' && Array.isArray(new_value)) {
        npcs[target_id] = { ...npc, status_effects: new_value };
      }
    }
  }

  return { ...gameState, characters, npcs, flags };
}

const initialState: SessionState = {
  sessionId: null,
  gameState: null,
  messages: [],
  events: [],
  connectionStatus: 'disconnected',
  isPaused: false,
  lastSequence: -1,
  awaitingHuman: null,
  streamingTokens: {},
};

function sessionReducer(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case 'SET_SESSION_ID':
      return { ...state, sessionId: action.payload };
    case 'SET_CONNECTION_STATUS':
      return { ...state, connectionStatus: action.payload };
    case 'SET_GAME_STATE':
      return { ...state, gameState: action.payload };
    case 'UPDATE_GAME_STATE':
      return {
        ...state,
        gameState: state.gameState ? { ...state.gameState, ...action.payload } : null,
      };
    case 'ADD_MESSAGE':
      return { ...state, messages: [...state.messages, action.payload] };
    case 'ADD_EVENT': {
      // Deduplicate events by id
      const exists = state.events.some((e) => e.id === action.payload.id);
      if (exists) return state;
      return { ...state, events: [...state.events, action.payload] };
    }
    case 'SET_PAUSED':
      return { ...state, isPaused: action.payload };
    case 'SET_SEQUENCE':
      return { ...state, lastSequence: action.payload };
    case 'SET_AWAITING_HUMAN':
      return { ...state, awaitingHuman: action.payload };
    case 'TAKEOVER_CHANGED': {
      if (!state.gameState) return state;
      const chars = { ...state.gameState.characters };
      const target = chars[action.payload.actor_id];
      if (target) {
        chars[action.payload.actor_id] = {
          ...target,
          controller: action.payload.new_controller,
        };
      }
      return {
        ...state,
        gameState: { ...state.gameState, characters: chars },
      };
    }
    case 'APPLY_STATE_PATCHES': {
      if (!state.gameState || !action.payload.length) return state;
      return {
        ...state,
        gameState: applyPatches(state.gameState, action.payload),
      };
    }
    case 'APPEND_STREAMING_TOKEN': {
      const { actorId, token } = action.payload;
      return {
        ...state,
        streamingTokens: {
          ...state.streamingTokens,
          [actorId]: (state.streamingTokens[actorId] || '') + token,
        },
      };
    }
    case 'CLEAR_STREAMING_TOKENS':
      return { ...state, streamingTokens: {} };
    case 'RESET':
      return { ...initialState, sessionId: state.sessionId };
    default:
      return state;
  }
}

interface SessionContextValue {
  state: SessionState;
  dispatch: React.Dispatch<SessionAction>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

interface SessionProviderProps {
  sessionId: string;
  children: ReactNode;
}

export function SessionProvider({ sessionId, children }: SessionProviderProps) {
  const [state, dispatch] = useReducer(sessionReducer, {
    ...initialState,
    sessionId,
  });

  useSessionStream(sessionId, dispatch);

  useEffect(() => {
    dispatch({ type: 'SET_SESSION_ID', payload: sessionId });
  }, [sessionId]);

  return (
    <SessionContext.Provider value={{ state, dispatch }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error('useSession must be used within a SessionProvider');
  }
  return context;
}

export type { SessionState, SessionAction };
