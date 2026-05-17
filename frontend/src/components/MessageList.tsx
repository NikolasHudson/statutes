import { useEffect, useRef } from 'react';
import Box from '@mui/material/Box';

import { MessageBubble } from './MessageBubble';
import type { Message } from '../types';

export function MessageList({ messages }: { messages: Message[] }) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  return (
    <Box sx={{ flex: 1, overflowY: 'auto', pb: 1 }}>
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
      <Box ref={endRef} sx={{ height: 12 }} />
    </Box>
  );
}
