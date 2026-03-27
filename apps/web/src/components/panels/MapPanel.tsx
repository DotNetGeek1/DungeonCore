import { useMemo, useState, useRef, useEffect } from 'react';
import { useSession } from '../../context/SessionContext';
import type {
  DungeonMap,
  MapTile,
  TerrainType,
  TileContent,
  Position,
  ActorStateBase,
  CharacterState,
  NpcState,
} from '../../types/generated';

const MIN_TILE_SIZE = 20;
const MAX_TILE_SIZE = 48;

const TERRAIN_COLORS: Record<TerrainType, string> = {
  floor: '#2a2a2e',
  wall: '#1a1a20',
  door: '#6b3a2a',
  door_locked: '#4a2020',
  stairs_up: '#2a4a6b',
  stairs_down: '#2a3a5a',
  difficult: '#3a3020',
  pit: '#0a0a0c',
  water_deep: '#1a2a4a',
};

const TERRAIN_BORDER_COLORS: Record<TerrainType, string> = {
  floor: '#3a3a40',
  wall: '#333338',
  door: '#8b5040',
  door_locked: '#6a3030',
  stairs_up: '#3a6a8b',
  stairs_down: '#3a5a7a',
  difficult: '#5a5030',
  pit: '#1a1a1e',
  water_deep: '#2a4a7a',
};

interface ContentStyle {
  symbol: string;
  color: string;
  shape: 'circle' | 'diamond' | 'square' | 'triangle' | 'dot' | 'text';
  bgColor?: string;
}

const CONTENT_STYLES: Record<TileContent, ContentStyle | null> = {
  empty: null,
  tree: { symbol: '🌿', color: '#3a7a3a', shape: 'circle', bgColor: '#1a3a1a' },
  altar: { symbol: '⛩', color: '#c084fc', shape: 'diamond', bgColor: '#2a1a3a' },
  treasure_chest: { symbol: '◆', color: '#fbbf24', shape: 'square', bgColor: '#2a2010' },
  campfire: { symbol: '●', color: '#f97316', shape: 'dot', bgColor: '#2a1a08' },
  pillar: { symbol: '⬛', color: '#9ca3af', shape: 'text', bgColor: undefined },
  statue: { symbol: '◈', color: '#c0c0c0', shape: 'text', bgColor: '#1a1a20' },
  barrel: { symbol: '⊕', color: '#92400e', shape: 'text', bgColor: undefined },
  table: { symbol: '▬', color: '#78350f', shape: 'text', bgColor: undefined },
  trap: { symbol: '▲', color: '#ef4444', shape: 'triangle', bgColor: '#2a0808' },
  trap_hidden: { symbol: '▲', color: '#991b1b', shape: 'triangle', bgColor: undefined },
  torch: { symbol: '●', color: '#fde68a', shape: 'dot', bgColor: '#2a2010' },
  rubble: { symbol: '∴', color: '#6b7280', shape: 'text', bgColor: undefined },
  bookshelf: { symbol: '▮', color: '#7c3aed', shape: 'text', bgColor: undefined },
  fountain: { symbol: '◉', color: '#60a5fa', shape: 'text', bgColor: '#0a1a2a' },
  lever: { symbol: '⊣', color: '#d97706', shape: 'text', bgColor: undefined },
};

const TERRAIN_SYMBOLS: Record<TerrainType, string> = {
  floor: '',
  wall: '',
  door: 'D',
  door_locked: 'L',
  stairs_up: '↑',
  stairs_down: '↓',
  difficult: '~',
  pit: '',
  water_deep: '≈',
};

interface ActorOverlay {
  id: string;
  name: string;
  label: string;
  role: string;
  hp: number;
  max_hp: number;
  color: string;
  borderColor: string;
}

function getActorColor(role: string, disposition?: string): { color: string; border: string } {
  if (role === 'player') return { color: '#22c55e', border: '#16a34a' };
  if (role === 'enemy' || disposition === 'hostile') return { color: '#ef4444', border: '#b91c1c' };
  if (disposition === 'ally') return { color: '#3b82f6', border: '#1d4ed8' };
  return { color: '#eab308', border: '#a16207' };
}

interface TileTooltip {
  x: number;
  y: number;
  tile: MapTile;
  actors: ActorOverlay[];
}

interface MapPanelProps {
  isDirector?: boolean;
}

export default function MapPanel({ isDirector = false }: MapPanelProps) {
  const { state } = useSession();
  const { gameState } = state;
  const [tooltip, setTooltip] = useState<TileTooltip | null>(null);
  const [hoveredTile, setHoveredTile] = useState<{ x: number; y: number } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  const dungeonMap = gameState?.dungeon_map;

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerSize({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const actorsByPosition = useMemo(() => {
    if (!gameState) return new Map<string, ActorOverlay[]>();

    const map = new Map<string, ActorOverlay[]>();
    const addActor = (actor: CharacterState | NpcState) => {
      if (!actor.position) return;
      // Skip dead actors (alive === false or hp <= 0)
      if (actor.alive === false || actor.hp <= 0) return;
      const key = `${actor.position.x},${actor.position.y}`;
      const { color, border } = getActorColor(
        actor.role,
        (actor as NpcState).disposition,
      );
      const label = actor.name.charAt(0).toUpperCase();
      const overlay: ActorOverlay = {
        id: actor.actor_id,
        name: actor.name,
        label,
        role: actor.role,
        hp: actor.hp,
        max_hp: actor.max_hp,
        color,
        borderColor: border,
      };
      const existing = map.get(key) ?? [];
      map.set(key, [...existing, overlay]);
    };

    Object.values(gameState.characters).forEach(addActor);
    Object.values(gameState.npcs).forEach(addActor);
    return map;
  }, [gameState]);

  const tileSize = useMemo(() => {
    if (!dungeonMap || containerSize.width === 0) return 32;
    const padding = 16;
    const gapTotal = dungeonMap.width;
    const availableWidth = containerSize.width - padding;
    const availableHeight = containerSize.height - padding;
    const tileSizeByWidth = Math.floor((availableWidth - gapTotal) / dungeonMap.width);
    const tileSizeByHeight = Math.floor((availableHeight - gapTotal) / dungeonMap.height);
    const computed = Math.min(tileSizeByWidth, tileSizeByHeight);
    return Math.max(MIN_TILE_SIZE, Math.min(MAX_TILE_SIZE, computed));
  }, [dungeonMap, containerSize]);

  if (!dungeonMap) {
    return (
      <div className="map-panel map-panel--empty">
        <div className="map-panel__header">
          <span className="map-panel__title">Dungeon Map</span>
        </div>
        <div className="map-panel__scroll" ref={scrollRef}>
          <div className="map-panel__no-map">
            <p>Map not yet revealed</p>
            <p className="map-panel__no-map-hint">The Dungeon Master will build the map as the story unfolds...</p>
          </div>
        </div>
      </div>
    );
  }

  function handleTileEnter(x: number, y: number, tile: MapTile) {
    setHoveredTile({ x, y });
    const key = `${x},${y}`;
    const actors = actorsByPosition.get(key) ?? [];
    setTooltip({ x, y, tile, actors });
  }

  function handleTileLeave() {
    setHoveredTile(null);
    setTooltip(null);
  }

  return (
    <div className="map-panel">
      <div className="map-panel__header">
        <span className="map-panel__title">⚔ {dungeonMap.name}</span>
        <span className="map-panel__size">{dungeonMap.width}×{dungeonMap.height}</span>
      </div>

      <div className="map-panel__scroll" ref={scrollRef}>
        <div
          className="map-panel__grid"
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${dungeonMap.width}, ${tileSize}px)`,
            gridTemplateRows: `repeat(${dungeonMap.height}, ${tileSize}px)`,
            gap: '1px',
            background: '#111114',
            padding: '4px',
          }}
        >
          {dungeonMap.tiles.map((row, y) =>
            row.map((tile, x) => {
              const isHovered = hoveredTile?.x === x && hoveredTile?.y === y;
              const actorKey = `${x},${y}`;
              const actors = actorsByPosition.get(actorKey) ?? [];
              const isRevealed = tile.revealed || isDirector;
              const terrainColor = TERRAIN_COLORS[tile.terrain] ?? '#2a2a2e';
              const borderColor = isHovered
                ? '#60a5fa'
                : TERRAIN_BORDER_COLORS[tile.terrain] ?? '#3a3a40';
              const contentStyle = tile.content !== 'empty'
                ? CONTENT_STYLES[tile.content]
                : null;
              const terrainSymbol = TERRAIN_SYMBOLS[tile.terrain];

              return (
                <div
                  key={`${x}-${y}`}
                  className="map-tile"
                  style={{
                    width: tileSize,
                    height: tileSize,
                    background: isRevealed ? terrainColor : '#0d0d10',
                    border: `1px solid ${isHovered ? '#60a5fa' : borderColor}`,
                    position: 'relative',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    overflow: 'hidden',
                    boxSizing: 'border-box',
                    transition: 'border-color 0.1s',
                  }}
                  onMouseEnter={() => handleTileEnter(x, y, tile)}
                  onMouseLeave={handleTileLeave}
                >
                  {isRevealed && (
                    <>
                      {/* Wall pattern */}
                      {tile.terrain === 'wall' && (
                        <div className="map-tile__wall-pattern" />
                      )}

                      {/* Water effect */}
                      {tile.terrain === 'water_deep' && (
                        <span style={{ fontSize: tileSize * 0.45, color: '#60a5fa', opacity: 0.7 }}>≈</span>
                      )}

                      {/* Terrain symbol (for special tiles without actors) */}
                      {terrainSymbol && actors.length === 0 && !contentStyle && (
                        <span style={{
                          fontSize: tileSize * 0.5,
                          color: '#94a3b8',
                          fontWeight: 'bold',
                          lineHeight: 1,
                        }}>
                          {terrainSymbol}
                        </span>
                      )}

                      {/* Content overlay */}
                      {contentStyle && actors.length === 0 && (
                        <div
                          style={{
                            width: tileSize * 0.65,
                            height: tileSize * 0.65,
                            background: contentStyle.bgColor ?? 'transparent',
                            borderRadius: contentStyle.shape === 'circle'
                              ? '50%'
                              : contentStyle.shape === 'diamond'
                              ? '0'
                              : contentStyle.shape === 'triangle'
                              ? '0'
                              : '2px',
                            transform: contentStyle.shape === 'diamond' ? 'rotate(45deg)' : 'none',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            border: contentStyle.bgColor ? `1px solid ${contentStyle.color}40` : 'none',
                          }}
                        >
                          <span style={{
                            fontSize: tileSize * 0.4,
                            color: contentStyle.color,
                            transform: contentStyle.shape === 'diamond' ? 'rotate(-45deg)' : 'none',
                            lineHeight: 1,
                          }}>
                            {contentStyle.symbol}
                          </span>
                        </div>
                      )}

                      {/* Actor overlays */}
                      {actors.length === 1 && (
                        <div
                          className="map-tile__actor"
                          style={{
                            width: tileSize * 0.75,
                            height: tileSize * 0.75,
                            borderRadius: '50%',
                            background: actors[0].color,
                            border: `2px solid ${actors[0].borderColor}`,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: tileSize * 0.38,
                            fontWeight: 'bold',
                            color: '#fff',
                            boxShadow: `0 0 6px ${actors[0].color}88`,
                          }}
                        >
                          {actors[0].label}
                        </div>
                      )}
                      {actors.length > 1 && (
                        <div style={{ display: 'flex', gap: '1px', flexWrap: 'wrap', justifyContent: 'center' }}>
                          {actors.slice(0, 4).map((a) => (
                            <div
                              key={a.id}
                              style={{
                                width: tileSize * 0.38,
                                height: tileSize * 0.38,
                                borderRadius: '50%',
                                background: a.color,
                                border: `1px solid ${a.borderColor}`,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                fontSize: tileSize * 0.22,
                                fontWeight: 'bold',
                                color: '#fff',
                              }}
                            >
                              {a.label}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* HP bar for actors */}
                      {actors.length === 1 && (
                        <div style={{
                          position: 'absolute',
                          bottom: 1,
                          left: 1,
                          right: 1,
                          height: 2,
                          background: '#1f1f23',
                          borderRadius: 1,
                          overflow: 'hidden',
                        }}>
                          <div style={{
                            height: '100%',
                            width: `${Math.round((actors[0].hp / actors[0].max_hp) * 100)}%`,
                            background: actors[0].hp / actors[0].max_hp > 0.5
                              ? '#22c55e'
                              : actors[0].hp / actors[0].max_hp > 0.25
                              ? '#f59e0b'
                              : '#ef4444',
                          }} />
                        </div>
                      )}
                    </>
                  )}

                  {/* Fog of war overlay for unrevealed tiles */}
                  {!isRevealed && (
                    <div style={{
                      position: 'absolute',
                      inset: 0,
                      background: '#0d0d10',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}>
                      {isDirector && (
                        <span style={{ fontSize: tileSize * 0.3, color: '#1f1f28', opacity: 0.5 }}>?</span>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div className="map-panel__tooltip">
          <div className="map-panel__tooltip-coord">({tooltip.x}, {tooltip.y})</div>
          <div className="map-panel__tooltip-terrain">{tooltip.tile.terrain}</div>
          {tooltip.tile.content !== 'empty' && (
            <div className="map-panel__tooltip-content">{tooltip.tile.content.replace(/_/g, ' ')}</div>
          )}
          {tooltip.tile.label && (
            <div className="map-panel__tooltip-label">{tooltip.tile.label}</div>
          )}
          {!tooltip.tile.revealed && !isDirector && (
            <div className="map-panel__tooltip-fog">Unexplored</div>
          )}
          {tooltip.actors.map((a) => (
            <div key={a.id} className="map-panel__tooltip-actor" style={{ color: a.color }}>
              {a.name} — HP {a.hp}/{a.max_hp}
            </div>
          ))}
        </div>
      )}

      {/* Legend */}
      <div className="map-panel__legend">
        <span className="map-panel__legend-item">
          <span className="map-panel__legend-dot" style={{ background: '#22c55e' }} />Player
        </span>
        <span className="map-panel__legend-item">
          <span className="map-panel__legend-dot" style={{ background: '#ef4444' }} />Enemy
        </span>
        <span className="map-panel__legend-item">
          <span className="map-panel__legend-dot" style={{ background: '#eab308' }} />NPC
        </span>
        <span className="map-panel__legend-item">
          <span className="map-panel__legend-swatch" style={{ background: TERRAIN_COLORS.wall }} />Wall
        </span>
        <span className="map-panel__legend-item">
          <span className="map-panel__legend-swatch" style={{ background: TERRAIN_COLORS.difficult }} />Difficult
        </span>
        <span className="map-panel__legend-item">
          <span className="map-panel__legend-swatch" style={{ background: '#0d0d10' }} />Fog
        </span>
      </div>
    </div>
  );
}
