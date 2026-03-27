import type {
  ActionSubmissionResponse,
  CreateSessionResponse,
  GetEventsResponse,
  GetSessionStateResponse,
  GetEventHistoryResponse,
  GetTracesResponse,
  GetVisibleMessagesResponse,
  OperatorCommandResponse,
  OverrideActionResponse,
  PlayerTurnSubmission,
  ReplayData,
  RerunNarrationResponse,
  StateEditResponse,
  TakeoverResponse,
  SessionListResponse,
  SessionHistoryResponse,
  SessionTranscriptResponse,
} from '../types/generated';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001';

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const options: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
    },
  };

  if (body) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(url, options);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`HTTP ${response.status}: ${errorText}`);
  }

  return response.json();
}

function GET<T>(path: string): Promise<T> {
  return request<T>('GET', path);
}

function POST<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('POST', path, body);
}

export const api = {
  createSession: (): Promise<CreateSessionResponse> =>
    POST('/sessions'),

  startMvpSession: (): Promise<any> =>
    POST('/sessions/start-mvp'),

  autoRun: (sessionId: string, turns: number = 3): Promise<any> =>
    POST(`/sessions/${sessionId}/auto-run?turns=${turns}`),

  runFullTurn: (sessionId: string): Promise<any> =>
    POST(`/sessions/${sessionId}/full-turn`),

  streamTurnUrl: (sessionId: string): string =>
    `${API_BASE}/sessions/${sessionId}/stream-turn`,

  streamPlayUrl: (sessionId: string, maxTurns: number = 20): string =>
    `${API_BASE}/sessions/${sessionId}/stream-play?max_turns=${maxTurns}`,

  getState: (sessionId: string): Promise<GetSessionStateResponse> =>
    GET(`/sessions/${sessionId}/state`),

  getEvents: (
    sessionId: string,
    params?: { limit?: number; event_type?: string; actor_id?: string }
  ): Promise<GetEventsResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.event_type) searchParams.set('event_type', params.event_type);
    if (params?.actor_id) searchParams.set('actor_id', params.actor_id);
    const query = searchParams.toString();
    return GET(`/sessions/${sessionId}/events${query ? `?${query}` : ''}`);
  },

  getTraces: (sessionId: string): Promise<GetTracesResponse> =>
    GET(`/sessions/${sessionId}/traces`),

  getReplayData: (sessionId: string): Promise<ReplayData> =>
    GET(`/sessions/${sessionId}/replay`),

  getMessages: (
    sessionId: string,
    actorId?: string
  ): Promise<GetVisibleMessagesResponse> => {
    const query = actorId ? `?actor_id=${actorId}` : '';
    return GET(`/sessions/${sessionId}/messages${query}`);
  },

  pause: (sessionId: string): Promise<OperatorCommandResponse> =>
    POST(`/sessions/${sessionId}/pause`),

  resume: (sessionId: string): Promise<OperatorCommandResponse> =>
    POST(`/sessions/${sessionId}/resume`),

  takeover: (
    sessionId: string,
    actorId: string
  ): Promise<TakeoverResponse> =>
    POST(`/sessions/${sessionId}/takeover`, { actor_id: actorId }),

  releaseTakeover: (
    sessionId: string,
    actorId: string
  ): Promise<TakeoverResponse> =>
    POST(`/sessions/${sessionId}/release-takeover`, { actor_id: actorId }),

  submitAction: (
    sessionId: string,
    actorId: string,
    turn: PlayerTurnSubmission
  ): Promise<ActionSubmissionResponse> =>
    POST(`/sessions/${sessionId}/submit-action`, {
      actor_id: actorId,
      source: 'human',
      turn,
    }),

  overrideAction: (
    sessionId: string,
    turn: PlayerTurnSubmission,
    reason?: string
  ): Promise<OverrideActionResponse> =>
    POST(`/sessions/${sessionId}/override-action`, { turn, reason }),

  editState: (
    sessionId: string,
    patches: Array<{ target_id: string; field: string; value: unknown }>,
    reason?: string
  ): Promise<StateEditResponse> =>
    request<StateEditResponse>('PATCH', `/sessions/${sessionId}/state`, {
      patches,
      reason: reason || 'director_edit',
    }),

  rerunNarration: (
    sessionId: string,
    reason?: string
  ): Promise<RerunNarrationResponse> =>
    POST(`/sessions/${sessionId}/rerun-narration`, { reason }),

  injectEvent: (
    sessionId: string,
    eventType: string,
    payload: unknown
  ): Promise<OperatorCommandResponse> =>
    POST(`/sessions/${sessionId}/inject-event`, {
      event_type: eventType,
      payload,
    }),

  listSessions: (params?: {
    status?: string;
    campaign_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<SessionListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.campaign_id) searchParams.set('campaign_id', params.campaign_id);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    const query = searchParams.toString();
    return GET(`/sessions${query ? `?${query}` : ''}`);
  },

  getSessionHistory: (sessionId: string, limit?: number): Promise<SessionHistoryResponse> => {
    const query = limit ? `?limit=${limit}` : '';
    return GET(`/sessions/${sessionId}/history${query}`);
  },

  getSessionTranscript: (sessionId: string): Promise<SessionTranscriptResponse> =>
    GET(`/sessions/${sessionId}/transcript`),

  startSession: (options: {
    campaign_id: string;
    scene_id: string;
    use_mvp_scenario?: boolean;
    generate_dynamic_map?: boolean;
    story_genre?: string;
    story_themes?: string[];
    map_complexity?: string;
  }): Promise<CreateSessionResponse> =>
    POST('/sessions/start', options),
};
