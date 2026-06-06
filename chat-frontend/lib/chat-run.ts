// Shared "chat turn" streaming logic: drive /api/chat/stream and translate its
// NDJSON events into assistant-ui message parts (a live progress tracker above
// the streamed answer, with a linked "Sources" footer on completion). Both the
// full-page Assistant (app/assistant.tsx) and the per-document chat panel
// (components/doc-chat.tsx) consume this so their turn behavior can't drift.

import type { ChatModelAdapter } from "@assistant-ui/react";

import type { ProgressStep } from "@/components/tool-ui/progress-tracker";
import { citationsMarkdown, streamChat, toolLabel } from "./iowa-chat";

type RunMessages = Parameters<ChatModelAdapter["run"]>[0]["messages"];

// Collapse assistant-ui's structured messages into the flat {role, content}
// shape the Django endpoint expects, dropping non-text parts (attachments,
// tool calls) and any roles the backend rejects.
export function flattenMessages(messages: RunMessages) {
  return messages
    .filter(
      (m) => m.role === "user" || m.role === "assistant" || m.role === "system",
    )
    .map((m) => ({
      role: m.role as "user" | "assistant" | "system",
      content:
        typeof m.content === "string"
          ? m.content
          : (m.content ?? [])
              .filter((p) => p.type === "text")
              .map((p) => (p as { type: "text"; text: string }).text)
              .join("\n"),
    }));
}

// Stable tool-call id for the progress tracker so re-emitting on each event
// updates the SAME tool part (assistant-ui dedupes by toolCallId) rather than
// stacking new cards in the message.
const PROGRESS_TOOL_CALL_ID = "iowa-progress";

type ProgressOutcome =
  | { kind: "running" }
  | { kind: "success" }
  | { kind: "failed"; reason: string }
  | { kind: "cancelled" };

export type ChatTurnScope = {
  model: string;
  sourceSlug: string | null;
  // When set, the turn is pinned to one document (case/statute node).
  nodeId?: number | null;
};

// Stream one chat turn, yielding assistant-ui content (`{ content: parts }`) as
// the answer and its progress tracker evolve. Mirrors the chat branch of the
// full-page adapter exactly; the only knob is `scope` (model / source / node).
export async function* runChatTurnParts(
  scope: ChatTurnScope,
  messages: RunMessages,
  abortSignal: AbortSignal,
) {
  const startedAt = Date.now();
  const steps: ProgressStep[] = [];
  let answer = "";
  let synthesisStarted = false;

  const elapsed = () => Date.now() - startedAt;

  const completeInProgress = () => {
    for (const s of steps) {
      if (s.status === "in-progress") s.status = "completed";
    }
  };

  const trackerPart = (outcome: ProgressOutcome) => ({
    type: "tool-call" as const,
    toolCallId: PROGRESS_TOOL_CALL_ID,
    toolName: "trackProgress",
    args: {},
    argsText: "{}",
    result: {
      id: "iowa-progress",
      steps: steps.map((s) => ({ ...s })),
      elapsedTime: elapsed(),
      ...(outcome.kind === "success"
        ? {
            choice: {
              outcome: "success" as const,
              summary: "Done — answer below.",
              at: new Date().toISOString(),
            },
          }
        : outcome.kind === "failed"
          ? {
              choice: {
                outcome: "failed" as const,
                summary: outcome.reason,
                at: new Date().toISOString(),
              },
            }
          : outcome.kind === "cancelled"
            ? {
                choice: {
                  outcome: "cancelled" as const,
                  summary: "Cancelled.",
                  at: new Date().toISOString(),
                },
              }
            : {}),
    },
  });

  const yieldState = (outcome: ProgressOutcome = { kind: "running" }) => {
    const parts: Array<
      ReturnType<typeof trackerPart> | { type: "text"; text: string }
    > = [];
    if (steps.length > 0) parts.push(trackerPart(outcome));
    if (answer) parts.push({ type: "text" as const, text: answer });
    return { content: parts };
  };

  try {
    for await (const event of streamChat(
      {
        model: scope.model,
        messages: flattenMessages(messages),
        source_slug: scope.sourceSlug,
        node_id: scope.nodeId ?? null,
      },
      abortSignal,
    )) {
      if (abortSignal.aborted) return;

      if (event.type === "tool_start") {
        completeInProgress();
        const { label, description } = toolLabel(event.name, event.arguments);
        steps.push({
          id: `step-${steps.length}`,
          label,
          ...(description ? { description } : {}),
          status: "in-progress",
        });
        yield yieldState();
      } else if (event.type === "delta") {
        // First delta = synthesis began. Mark any in-progress tool step as
        // complete; the streaming text below the tracker is its own visual cue
        // that drafting is underway — no need for a step.
        if (!synthesisStarted) {
          synthesisStarted = true;
          completeInProgress();
        }
        answer += event.text;
        yield yieldState();
      } else if (event.type === "done") {
        for (const s of steps) {
          if (s.status === "in-progress" || s.status === "pending") {
            s.status = "completed";
          }
        }
        answer =
          (answer || "(no answer returned)") +
          citationsMarkdown(event.tool_calls ?? [], answer);
        yield yieldState({ kind: "success" });
        return;
      } else if (event.type === "error") {
        for (const s of steps) {
          if (s.status === "in-progress") s.status = "failed";
        }
        answer = `The request failed: ${event.message}`;
        yield yieldState({ kind: "failed", reason: event.message });
        return;
      }
    }
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    for (const s of steps) {
      if (s.status === "in-progress") s.status = "failed";
    }
    answer = `The request failed: ${(e as Error).message ?? String(e)}`;
    yield yieldState({
      kind: "failed",
      reason: (e as Error).message ?? String(e),
    });
  }
}
