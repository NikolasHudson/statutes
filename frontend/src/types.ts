export type Citation = {
  id: string;
  citation: string; // e.g. "Iowa Code § 562A.15"
  heading: string; // e.g. "Landlord to maintain fit premises"
  source: 'Iowa Code' | 'Iowa Court Rules' | 'Iowa Admin. Code';
  url: string; // canonical link to legis.iowa.gov etc.
  effectiveFrom: string; // ISO date
  enactedBy?: string; // session law ref
  snippet?: string;
  relevance?: number; // 0..1
};

export type Message = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string; // ISO
  citations?: Citation[];
  pending?: boolean;
};

export type Conversation = {
  id: string;
  title: string;
  updatedAt: string; // ISO
  messages: Message[];
  pinned?: boolean;
};
