/**
 * Generated TypeScript types from shared-schemas
 * These types mirror the Pydantic models in packages/shared-schemas
 */

export type EntityId = string;
export type TraceId = string;
export type CorrelationId = string;
export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export type ScenePhase =
  | 'scene_intro'
  | 'discussion'
  | 'action_commit'
  | 'resolution'
  | 'narration'
  | 'reaction'
  | 'turn_end';

export type SessionStatus = 'created' | 'running' | 'paused' | 'completed' | 'error';

export type MessageChannel = 'in_character' | 'table_talk' | 'private_whisper' | 'dm_notice';

export type Visibility = 'public' | 'party' | 'private' | 'dm_only';

export type ActorRole = 'player' | 'npc' | 'enemy' | 'dm';

export type TerrainType =
  | 'floor'
  | 'wall'
  | 'door'
  | 'door_locked'
  | 'stairs_up'
  | 'stairs_down'
  | 'difficult'
  | 'pit'
  | 'water_deep';

export type TileContent =
  | 'empty'
  | 'tree'
  | 'altar'
  | 'treasure_chest'
  | 'campfire'
  | 'pillar'
  | 'statue'
  | 'barrel'
  | 'table'
  | 'trap'
  | 'trap_hidden'
  | 'torch'
  | 'rubble'
  | 'bookshelf'
  | 'fountain'
  | 'lever';

export interface MapTile {
  terrain: TerrainType;
  content: TileContent;
  revealed: boolean;
  label?: string | null;
  elevation: number;
}

export interface DungeonMap {
  name: string;
  width: number;
  height: number;
  tiles: MapTile[][];
  default_terrain: TerrainType;
}

export interface Position {
  x: number;
  y: number;
  node_id?: string | null;
  zone_id?: string | null;
}

export type ControllerType = 'agent' | 'human' | 'operator';

export interface ActorStateBase {
  actor_id: EntityId;
  name: string;
  role: ActorRole;
  hp: number;
  max_hp: number;
  ac: number;
  initiative: number;
  position?: Position;
  status_effects: string[];
  alive: boolean;
  controller?: ControllerType;
}

export interface CharacterState extends ActorStateBase {
  role: 'player';
  inventory: string[];
  spell_slots: Record<string, number>;
}

export interface NpcState extends ActorStateBase {
  role: 'npc' | 'enemy';
  disposition?: string;
}

export interface SceneState {
  scene_id: EntityId;
  name: string;
  summary: string;
  phase: ScenePhase;
  turn_number: number;
  active_actor_id: EntityId | null;
  location_name?: string;
}

export interface TurnState {
  turn_number: number;
  round_number: number;
  active_actor_id: EntityId | null;
  phase: ScenePhase;
  discussion_open: boolean;
  max_discussion_messages: number;
  remaining_discussion_messages: number;
}

export interface ObjectiveState {
  objective_id: EntityId;
  label: string;
  summary?: string | null;
  status: 'active' | 'completed' | 'failed';
}

export interface GameState {
  schema_version: string;
  campaign_id: EntityId;
  session_id: EntityId;
  scene: SceneState;
  turn: TurnState;
  characters: Record<EntityId, CharacterState>;
  npcs: Record<EntityId, NpcState>;
  objectives: ObjectiveState[];
  flags: Record<string, string | number | boolean>;
  dungeon_map?: DungeonMap | null;
}

export interface TableMessage {
  id: EntityId;
  turn_number: number;
  phase: ScenePhase;
  channel: MessageChannel;
  sender_id: EntityId;
  sender_name: string;
  recipient_ids: EntityId[] | 'all';
  visibility: Visibility;
  text: string;
  created_at: string;
}

export interface ActionPayload {
  type: string;
  target_id?: EntityId;
  movement_path?: string[];
  item_id?: string;
  spell_id?: string;
  extra?: Record<string, unknown>;
}

export interface TileChange {
  x: number;
  y: number;
  terrain?: TerrainType | null;
  content?: TileContent | null;
  revealed?: boolean | null;
  label?: string | null;
  elevation?: number | null;
}

export interface DiceRoll {
  dice_type: string;
  count: number;
  results: number[];
  total: number;
  modifier: number;
  purpose: string;
}

export type EventType =
  | 'session.started'
  | 'scene.started'
  | 'discussion.opened'
  | 'discussion.closed'
  | 'message.created'
  | 'action.proposed'
  | 'action.validated'
  | 'action.awaiting_human'
  | 'action.resolved'
  | 'dice.rolled'
  | 'state.updated'
  | 'narration.emitted'
  | 'takeover.changed'
  | 'turn.ended'
  | 'map.updated';

export interface EventEnvelopeBase {
  id: EntityId;
  session_id: EntityId;
  turn_number: number;
  trace_id: TraceId;
  correlation_id: CorrelationId;
  created_at: string;
}

export interface SessionStartedPayload {
  session_id: EntityId;
  campaign_id: EntityId;
  started_by: EntityId | null;
  initial_state: GameState;
  created_at: string;
}

export interface SessionStartedEvent extends EventEnvelopeBase {
  event_type: 'session.started';
  payload: SessionStartedPayload;
}

export interface SceneStartedPayload {
  scene_id: EntityId;
  scene_name: string;
  scene_summary: string;
  phase: ScenePhase;
}

export interface SceneStartedEvent extends EventEnvelopeBase {
  event_type: 'scene.started';
  payload: SceneStartedPayload;
}

export interface DiscussionWindowPayload {
  discussion_open: boolean;
  max_messages: number;
  remaining_messages: number;
}

export interface DiscussionOpenedEvent extends EventEnvelopeBase {
  event_type: 'discussion.opened';
  payload: DiscussionWindowPayload;
}

export interface DiscussionClosedEvent extends EventEnvelopeBase {
  event_type: 'discussion.closed';
  payload: DiscussionWindowPayload;
}

export interface MessageCreatedPayload {
  message: TableMessage;
}

export interface MessageCreatedEvent extends EventEnvelopeBase {
  event_type: 'message.created';
  payload: MessageCreatedPayload;
}

export interface ActionProposedPayload {
  actor_id: EntityId;
  action: ActionPayload;
  speech?: string;
  table_talk?: string;
}

export interface ActionProposedEvent extends EventEnvelopeBase {
  event_type: 'action.proposed';
  payload: ActionProposedPayload;
}

export interface ActionValidatedPayload {
  actor_id: EntityId;
  action: ActionPayload;
  valid: boolean;
  errors: string[];
  normalized_action?: ActionPayload;
}

export interface ActionValidatedEvent extends EventEnvelopeBase {
  event_type: 'action.validated';
  payload: ActionValidatedPayload;
}

export interface ActionResolvedPayload {
  actor_id: EntityId;
  action: ActionPayload;
  resolution_type: string;
  effects: Record<string, unknown>[];
  state_patch: Partial<GameState>;
}

export interface ActionResolvedEvent extends EventEnvelopeBase {
  event_type: 'action.resolved';
  payload: ActionResolvedPayload;
}

export interface DiceRolledPayload {
  actor_id: EntityId;
  rolls: DiceRoll[];
  context: string;
}

export interface DiceRolledEvent extends EventEnvelopeBase {
  event_type: 'dice.rolled';
  payload: DiceRolledPayload;
}

export interface StateUpdatedPayload {
  patch: Partial<GameState>;
  reason: string;
}

export interface StateUpdatedEvent extends EventEnvelopeBase {
  event_type: 'state.updated';
  payload: StateUpdatedPayload;
}

export interface NarrationEmittedPayload {
  narrator_id: EntityId;
  text: string;
  style?: string;
}

export interface NarrationEmittedEvent extends EventEnvelopeBase {
  event_type: 'narration.emitted';
  payload: NarrationEmittedPayload;
}

export type ActionTypeEnum =
  | 'attack'
  | 'move'
  | 'move_and_attack'
  | 'defend'
  | 'inspect'
  | 'cast_spell_basic'
  | 'update_map';

export interface ActionAwaitingHumanPayload {
  actor_id: EntityId;
  allowed_actions: ActionTypeEnum[];
  timeout_seconds: number;
}

export interface ActionAwaitingHumanEvent extends EventEnvelopeBase {
  event_type: 'action.awaiting_human';
  payload: ActionAwaitingHumanPayload;
}

export interface TakeoverChangedPayload {
  actor_id: EntityId;
  new_controller: ControllerType;
  previous_controller: ControllerType;
}

export interface TakeoverChangedEvent extends EventEnvelopeBase {
  event_type: 'takeover.changed';
  payload: TakeoverChangedPayload;
}

export interface TurnEndedPayload {
  turn_number: number;
  next_active_actor_id: EntityId | null;
  next_phase: ScenePhase;
}

export interface TurnEndedEvent extends EventEnvelopeBase {
  event_type: 'turn.ended';
  payload: TurnEndedPayload;
}

export interface MapUpdatedPayload {
  map_name: string;
  changes_count: number;
  full_map_included: boolean;
}

export interface MapUpdatedEvent extends EventEnvelopeBase {
  event_type: 'map.updated';
  payload: MapUpdatedPayload;
}

export type GameEvent =
  | SessionStartedEvent
  | SceneStartedEvent
  | DiscussionOpenedEvent
  | DiscussionClosedEvent
  | MessageCreatedEvent
  | ActionProposedEvent
  | ActionValidatedEvent
  | ActionAwaitingHumanEvent
  | ActionResolvedEvent
  | DiceRolledEvent
  | StateUpdatedEvent
  | NarrationEmittedEvent
  | TakeoverChangedEvent
  | TurnEndedEvent
  | MapUpdatedEvent;

export interface WebSocketEventEnvelope {
  schema_version: string;
  session_id: EntityId;
  sequence_number: number;
  event: GameEvent;
}

export interface SessionSummary {
  session_id: EntityId;
  campaign_id: EntityId;
  scene_id: EntityId;
  status: SessionStatus;
}

export interface CreateSessionResponse {
  session: SessionSummary;
  state: GameState;
}

export interface GetSessionStateResponse {
  session_id: EntityId;
  state: GameState;
}

export interface GetEventHistoryResponse {
  session_id: EntityId;
  events: GameEvent[];
  next_cursor?: string;
}

export interface GetVisibleMessagesResponse {
  session_id: EntityId;
  messages: TableMessage[];
}

export interface OperatorCommandResponse {
  session_id: EntityId;
  command_type: string;
  accepted: boolean;
  status: string;
  event?: GameEvent;
}

export interface HealthResponse {
  service: string;
  status: 'ok' | 'degraded';
  port: number;
  dependencies: {
    postgres: boolean;
    redis: boolean;
    rabbitmq: boolean;
  };
}

export interface TakeoverResponse {
  session_id: EntityId;
  actor_id: EntityId;
  accepted: boolean;
  new_controller: ControllerType;
  message?: string;
}

export interface ActionSubmissionResponse {
  session_id: EntityId;
  accepted: boolean;
  action_status: 'queued' | 'rejected' | 'validated';
  normalized_action?: ActionPayload;
}

export interface OverrideActionResponse {
  session_id: EntityId;
  accepted: boolean;
  message?: string;
}

export interface StateEditResponse {
  session_id: EntityId;
  accepted: boolean;
  patches_applied: number;
  message?: string;
}

export interface RerunNarrationResponse {
  session_id: EntityId;
  accepted: boolean;
  narration_text?: string;
  message?: string;
}

export interface PlayerTurnSubmission {
  thought?: string;
  speech?: string;
  table_talk?: string;
  action?: ActionPayload;
}

export interface AgentInvocationRecord {
  agent_id: string;
  role: string;
  latency_ms: number;
  validation_result: string;
  retries: number;
  error?: string;
}

export interface TurnTrace {
  session_id: string;
  turn_number: number;
  active_actor_id: string | null;
  context_summary: string;
  phase_sequence: string[];
  agent_invocations: AgentInvocationRecord[];
  action_proposed: string | null;
  action_validated: boolean | null;
  action_resolved: string | null;
  narration_summary: string | null;
  total_latency_ms: number;
  started_at: string;
  completed_at: string | null;
  errors: string[];
}

export interface GetTracesResponse {
  session_id: string;
  traces: TurnTrace[];
  total: number;
}

export interface ReplayData {
  session_id: string;
  initial_state: GameState | null;
  events: GameEvent[];
  total_events: number;
  total_turns: number;
}

export interface GetEventsResponse {
  session_id: string;
  events: GameEvent[];
  total: number;
}

export interface SessionListItem {
  session_id: string;
  campaign_id: string;
  scene_id: string;
  scene_name?: string;
  status: SessionStatus;
  turn_number?: number;
  phase?: ScenePhase;
  started_at?: string;
  paused_at?: string;
  source: 'memory' | 'database';
}

export interface SessionListResponse {
  sessions: SessionListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface EventHistoryItem {
  id: string;
  event_type: string;
  turn_number: number;
  created_at: string;
  payload: Record<string, unknown>;
}

export interface SnapshotSummary {
  snapshot_id: string;
  session_id: string;
  turn_number: number;
  phase: ScenePhase;
  created_at: string;
}

export interface SessionHistoryResponse {
  session_id: string;
  status: string;
  events: EventHistoryItem[];
  snapshots: SnapshotSummary[];
  total_events: number;
  total_snapshots: number;
}

export interface SessionTranscriptResponse {
  session_id: string;
  transcript: string;
  turn_count: number;
  generated_at: string;
}
