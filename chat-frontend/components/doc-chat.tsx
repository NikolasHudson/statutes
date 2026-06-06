"use client";

// Per-document chat: a right-docked panel that talks to the same /api/chat
// pipeline as the full-page assistant, but pinned to the one node the user is
// reading (a statute section / court rule, or a caselaw decision). Opened by
// pressing "/" anywhere on the page — guarded so it never fires while the user
// is typing in a field. Mount one per document page, keyed by node id so a new
// document starts a fresh conversation:
//
//   {node ? <DocChat key={node.id} nodeId={node.id} title={…} citation={…} /> : null}

import {
  AssistantRuntimeProvider,
  type ChatModelAdapter,
  useLocalRuntime,
} from "@assistant-ui/react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Thread } from "@/components/assistant-ui/thread";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { runChatTurnParts } from "@/lib/chat-run";

// Model the panel spends on. Kept to the app default (a reasoning model tuned
// for the corpus) rather than exposing a selector — the panel is meant to be a
// quick, focused aside, not the full console. Must be in ALLOWED_CHAT_MODELS.
const DOC_CHAT_MODEL = "gpt-5-mini";

// Pinned to one document; corpus search stays unrestricted (source_slug=null)
// so a case can pull the statutes it cites and a statute can surface related
// authority. The pin is the document, not the search scope.
function makeDocAdapter(nodeId: number): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }) {
      yield* runChatTurnParts(
        { model: DOC_CHAT_MODEL, sourceSlug: null, nodeId },
        messages,
        abortSignal,
      );
    },
  };
}

export function DocChat({
  nodeId,
  title,
  citation,
  kind = "statute",
}: {
  nodeId: number;
  // Human label for the panel header — section heading or case name.
  title: string;
  // Canonical citation, shown emphasized in the header when available.
  citation?: string;
  kind?: "statute" | "case";
}) {
  const [open, setOpen] = useState(false);
  // The keydown listener is attached once; read `open` through a ref so it
  // doesn't re-subscribe on every toggle (and so we can bail when already open
  // without making the effect depend on `open`).
  const openRef = useRef(open);
  openRef.current = open;

  const runtime = useLocalRuntime(
    useMemo(() => makeDocAdapter(nodeId), [nodeId]),
  );

  // Global "/" opens the panel. Ignore it when a modifier is held or when the
  // user is typing somewhere — otherwise "/" in any search box would hijack to
  // the panel. Once open, the composer owns "/" (its slash menu), and this
  // listener bails because focus is inside the textarea.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (openRef.current) return;
      const el = e.target as HTMLElement | null;
      if (
        el &&
        (el.tagName === "INPUT" ||
          el.tagName === "TEXTAREA" ||
          el.tagName === "SELECT" ||
          el.isContentEditable)
      ) {
        return;
      }
      e.preventDefault();
      setOpen(true);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const label = kind === "case" ? "case" : "section";

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent
        side="right"
        // Wider than the default sheet so the answer + progress tracker have
        // room; remove the default padding since the Thread manages its own.
        className="flex w-full flex-col gap-0 p-0 sm:max-w-xl"
      >
        <SheetHeader className="gap-1 border-b px-4 py-3 pr-12">
          <SheetTitle className="text-sm">Ask about this {label}</SheetTitle>
          <SheetDescription className="truncate text-xs">
            {citation ? (
              <span className="font-medium text-foreground">{citation}</span>
            ) : null}
            {citation && title ? " — " : ""}
            {title}
          </SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1">
          <AssistantRuntimeProvider runtime={runtime}>
            <Thread
              composerPlaceholder={`Ask about ${citation || title}…`}
            />
          </AssistantRuntimeProvider>
        </div>
      </SheetContent>
    </Sheet>
  );
}
