import { useRef, useEffect } from 'react';
import { useSession } from '../../context/SessionContext';
import MessageBubble from '../MessageBubble';
import type { TableMessage } from '../../types/generated';

export default function TacticalChatPanel() {
  const { state } = useSession();
  const { messages, events, gameState } = state;
  const scrollRef = useRef<HTMLDivElement>(null);

  const actorName = (id: string): string => {
    if (!gameState) return id;
    const char = gameState.characters[id];
    if (char) return char.name;
    const npc = gameState.npcs[id];
    if (npc) return npc.name;
    return id;
  };

  const directMessages = messages.filter((m) => m.channel === 'table_talk');

  const eventMessages: TableMessage[] = events
    .filter((e) => e.event_type === 'message.created' && (e as any).payload?.message)
    .map((e) => (e as any).payload.message as TableMessage)
    .filter((m) => m.channel === 'table_talk');

  const seenIds = new Set<string>();
  const dedup = (m: TableMessage): boolean => {
    if (seenIds.has(m.id)) return false;
    seenIds.add(m.id);
    return true;
  };

  const allMessages = [...directMessages, ...eventMessages]
    .filter(dedup)
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [allMessages.length]);

  return (
    <div className="panel tactical-chat-panel">
      <h3 className="panel-title">Tactical Chat ({allMessages.length})</h3>
      <div className="chat-content" ref={scrollRef}>
        {allMessages.length === 0 ? (
          <p className="empty-state">No table talk messages yet.</p>
        ) : (
          allMessages.map((message) => {
            const msg = { ...message, sender_name: actorName(message.sender_id) };
            return <MessageBubble key={msg.id} message={msg} compact />;
          })
        )}
      </div>
    </div>
  );
}
