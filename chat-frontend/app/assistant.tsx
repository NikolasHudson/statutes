"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  type ChatModelAdapter,
} from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/thread";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { ThreadListSidebar } from "@/components/assistant-ui/threadlist-sidebar";
import { Separator } from "@/components/ui/separator";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { ModelSelector } from "@/components/assistant-ui/model-selector";
import { Select } from "@/components/assistant-ui/select";
import {
  citationsMarkdown,
  fetchSources,
  streamChat,
  toolLabel,
  type BrowseSource,
} from "@/lib/iowa-chat";
import type { ProgressStep } from "@/components/tool-ui/progress-tracker";

// Must stay in sync with ALLOWED_CHAT_MODELS in apps/api/chat.py.
const CHAT_MODELS = [
  {
    id: "gpt-5-mini",
    name: "GPT-5 Mini",
    description: "Best accuracy on Iowa Court Rules. Reasoning model.",
  },
  {
    id: "gpt-4o",
    name: "GPT-4o",
    description: "Fast, classic chat model.",
  },
  {
    id: "gpt-4o-mini",
    name: "GPT-4o Mini",
    description: "Cheapest. Acceptable for simple lookups.",
  },
] as const;

const DEFAULT_SCOPE = "iowa-court-rules";
// Radix's <Select.Item> rejects value="" (it reserves the empty string for
// the cleared/placeholder state). Use a sentinel and translate at the API
// boundary instead.
const SCOPE_ALL = "all";

function flattenMessages(
  messages: readonly Parameters<ChatModelAdapter["run"]>[0]["messages"][number][],
) {
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

function makeAdapter(
  getScope: () => { model: string; sourceSlug: string | null },
): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }) {
      const scope = getScope();
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
          },
          abortSignal,
        )) {
          if (abortSignal.aborted) return;

          if (event.type === "tool_start") {
            completeInProgress();
            const { label, description } = toolLabel(
              event.name,
              event.arguments,
            );
            steps.push({
              id: `step-${steps.length}`,
              label,
              ...(description ? { description } : {}),
              status: "in-progress",
            });
            yield yieldState();
          } else if (event.type === "delta") {
            // First delta = synthesis began. Mark any in-progress tool step
            // as complete; the streaming text below the tracker is its own
            // visual cue that drafting is underway — no need for a step.
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
    },
  };
}

export const Assistant = () => {
  const [model, setModel] = useState<string>(CHAT_MODELS[0].id);
  const [scope, setScope] = useState<string>(DEFAULT_SCOPE);
  const [sources, setSources] = useState<BrowseSource[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetchSources().then((s) => {
      if (!cancelled) setSources(s);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Wrap state in a ref-style getter so the adapter (memoized once) always
  // sees the latest model/scope without re-instantiating the runtime.
  const sourceSlug = scope === SCOPE_ALL ? null : scope;
  const scopeRef = useMemo(
    () => ({ current: { model, sourceSlug } }),
    [],
  );
  scopeRef.current = { model, sourceSlug };
  const adapter = useMemo(() => makeAdapter(() => scopeRef.current), [scopeRef]);
  const runtime = useLocalRuntime(adapter);

  const activeSourceName = useMemo(
    () => sources.find((s) => s.slug === scope)?.name ?? "All sources",
    [sources, scope],
  );

  const scopeOptions = useMemo(
    () => [
      { value: SCOPE_ALL, label: "All sources" },
      ...sources.map((s) => ({ value: s.slug, label: s.name })),
    ],
    [sources],
  );

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <SidebarProvider>
        <div className="flex h-dvh w-full pr-0.5">
          <ThreadListSidebar />
          <SidebarInset>
            <header className="flex h-16 shrink-0 items-center gap-3 border-b px-4">
              <SidebarTrigger />
              <Separator orientation="vertical" className="mr-2 h-4" />
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem className="hidden md:block">
                    Iowa Legal Corpus
                  </BreadcrumbItem>
                  <BreadcrumbSeparator className="hidden md:block" />
                  <BreadcrumbItem>
                    <BreadcrumbPage>{activeSourceName}</BreadcrumbPage>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>

              <div className="ml-auto flex items-center gap-2">
                <Select
                  value={scope}
                  onValueChange={setScope}
                  options={scopeOptions}
                  placeholder="Source"
                />
                <ModelSelector
                  models={CHAT_MODELS as unknown as { id: string; name: string; description?: string }[]}
                  value={model}
                  onValueChange={setModel}
                  size="sm"
                  variant="outline"
                />
              </div>
            </header>
            <div className="flex-1 overflow-hidden">
              <Thread />
            </div>
          </SidebarInset>
        </div>
      </SidebarProvider>
    </AssistantRuntimeProvider>
  );
};
