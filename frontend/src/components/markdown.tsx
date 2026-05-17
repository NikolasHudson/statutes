import { Fragment, type ReactNode } from 'react';
import Box from '@mui/material/Box';

// Tiny renderer for the subset of formatting we generate locally:
//   **bold**, *italic*, `code`, and Iowa-style citations like "§ 562A.15"
// Real backend output should be sanitized server-side; keep this dependency-free for now.

const tokenRe = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;

function renderInline(text: string, key: string): ReactNode {
  const parts = text.split(tokenRe).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={`${key}-${i}`} style={{ fontWeight: 600 }}>
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('*') && part.endsWith('*')) {
      return <em key={`${key}-${i}`}>{part.slice(1, -1)}</em>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <Box
          component="code"
          key={`${key}-${i}`}
          sx={{
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: '0.92em',
            px: 0.5,
            py: 0.1,
            borderRadius: 0.75,
            bgcolor: (t) =>
              t.palette.mode === 'light' ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.08)',
          }}
        >
          {part.slice(1, -1)}
        </Box>
      );
    }
    return <Fragment key={`${key}-${i}`}>{part}</Fragment>;
  });
}

export function MarkdownText({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/);
  return (
    <>
      {paragraphs.map((p, i) => (
        <Box
          key={i}
          component="p"
          sx={{
            m: 0,
            mb: i < paragraphs.length - 1 ? 1.5 : 0,
            lineHeight: 1.7,
            fontSize: 15.5,
          }}
        >
          {renderInline(p, `p${i}`)}
        </Box>
      ))}
    </>
  );
}
