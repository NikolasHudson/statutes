"use client";

import { useMemo } from "react";
import {
  ArrowUpIcon,
  BotIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CopyIcon,
  DownloadIcon,
  LoaderIcon,
  PencilIcon,
  RefreshCwIcon,
  SlidersHorizontalIcon,
  SquareIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
  UserIcon,
  XIcon,
} from "lucide-react";
import {
  ActionBarPrimitive,
  AuiIf,
  BranchPickerPrimitive,
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  unstable_useSlashCommandAdapter,
} from "@assistant-ui/react";
import "@assistant-ui/react-markdown/styles/dot.css";

import { Button } from "@/components/ui/button";
import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";
import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { ToolFallback } from "@/components/assistant-ui/tool-fallback";
import {
  ReasoningContent,
  ReasoningRoot,
  ReasoningText,
  ReasoningTrigger,
} from "@/components/assistant-ui/reasoning";
import { useAuth } from "@/components/auth-gate";
import { ProgressTracker } from "@/components/tool-ui/progress-tracker";
import { safeParseSerializableProgressTracker } from "@/components/tool-ui/progress-tracker/schema";
import {
  CitationChecklist,
  checklistResultToProps,
} from "@/components/tool-ui/citation-checklist/citation-checklist";
import {
  ComposerAddAttachment,
  ComposerAttachments,
  UserMessageAttachments,
} from "@/components/assistant-ui/attachment";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

// A selectable tool surfaced in the composer's slash menu, Tools dropdown, and
// (when active) the pill above the input. "Chat" is the absence of a tool, so
// it is NOT a member of this list — clearing the active tool returns to chat.
export type ComposerTool = {
  id: string;
  label: string;
  description: string;
  icon?: React.ComponentType<{ className?: string }>;
};

export function Thread({
  composerPlaceholder,
  tools = [],
  activeTool,
  onSelectTool,
}: {
  composerPlaceholder?: string;
  tools?: readonly ComposerTool[];
  activeTool?: string | null;
  onSelectTool?: (id: string) => void;
} = {}) {
  return (
    <ThreadPrimitive.Root
      className="flex h-full flex-col bg-background text-base"
      // CSS custom properties aren't in React.CSSProperties' typed union;
      // cast so production `next build` (strict typecheck) accepts them.
      style={
        {
          "--thread-max-width": "48rem",
          "--accent-color": "#2563eb",
          "--accent-foreground": "#ffffff",
          // Consumed by the attachment tile's rounded-[calc(...)] in
          // attachment.tsx. Without these the calc is invalid and the browser
          // drops border-radius entirely (square tiles). 24px matches the
          // composer's rounded-3xl; 14px (24-10) is the resulting tile radius.
          "--composer-radius": "24px",
          "--composer-padding": "10px",
        } as React.CSSProperties
      }
    >
      <ThreadPrimitive.Viewport
        turnAnchor="top"
        className="relative flex flex-1 flex-col overflow-x-auto overflow-y-scroll scroll-smooth px-4 pt-4"
      >
        <AuiIf condition={(s) => s.thread.isEmpty}>
          <ThreadWelcome />
        </AuiIf>

        <ThreadPrimitive.Messages
          components={{
            UserMessage,
            EditComposer,
            AssistantMessage,
          }}
        />

        <ThreadPrimitive.ViewportFooter className="sticky bottom-0 mx-auto mt-auto flex w-full max-w-[var(--thread-max-width)] flex-col gap-4 overflow-visible rounded-t-3xl bg-background pb-4">
          
          <Composer
            placeholder={composerPlaceholder}
            tools={tools}
            activeTool={activeTool}
            onSelectTool={onSelectTool}
          />
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
}
function ThreadWelcome() {
  const { user } = useAuth();
  // Take the first word of full_name when set, otherwise the local-part of
  // the email up to the first separator. Title-case so "nick" → "Nick".
  const raw =
    user.full_name?.trim().split(/\s+/)[0] ||
    user.email.split("@")[0].split(/[._-]/)[0];
  const firstName = raw
    ? raw[0].toUpperCase() + raw.slice(1).toLowerCase()
    : "";

  return (
    <div className="mx-auto my-auto flex w-full max-w-[var(--thread-max-width)] flex-grow flex-col">
      <div className="flex w-full flex-grow flex-col items-center justify-center">
        <div className="flex size-full flex-col justify-center px-8">
          <div className="text-2xl font-semibold">
            Hello{firstName ? `, ${firstName}` : ""}!
          </div>
          <div className="text-2xl text-muted-foreground/65">
            How can I help you today?
          </div>
        </div>
      </div>

    </div>
  );
}

function Composer({
  placeholder,
  tools = [],
  activeTool,
  onSelectTool,
}: {
  placeholder?: string;
  tools?: readonly ComposerTool[];
  activeTool?: string | null;
  onSelectTool?: (id: string) => void;
} = {}) {
  // Slash-command menu: typing "/" in the composer opens a menu of tools.
  // Selecting one runs its `execute` (switch chat mode); `removeOnExecute`
  // strips the "/verify" text so the composer is clean for the document. The
  // list is derived from `tools` plus a trailing "Chat" entry that clears any
  // active tool — same set of choices as the Tools dropdown below.
  const slash = unstable_useSlashCommandAdapter({
    commands: useMemo(
      () => [
        ...tools.map((t) => ({
          id: t.id,
          label: t.label,
          description: t.description,
          execute: () => onSelectTool?.(t.id),
        })),
        {
          id: "chat",
          label: "Chat",
          description: "Ask questions about the Iowa Code and Court Rules",
          execute: () => onSelectTool?.("chat"),
        },
      ],
      [tools, onSelectTool],
    ),
    removeOnExecute: true,
  });

  const active = tools.find((t) => t.id === activeTool) ?? null;

  return (
    <ComposerPrimitive.Root className="relative flex w-full flex-col">
      <ComposerPrimitive.Unstable_TriggerPopoverRoot>
        <ComposerPrimitive.AttachmentDropzone className="flex w-full flex-col rounded-3xl border border-input bg-background px-1 pt-2 outline-none transition-shadow has-[textarea:focus-visible]:border-ring has-[textarea:focus-visible]:ring-2 has-[textarea:focus-visible]:ring-ring/20 data-[dragging=true]:border-ring data-[dragging=true]:border-dashed data-[dragging=true]:bg-accent/50">
          <ComposerAttachments />
          {active && (
            <ActiveToolPill
              tool={active}
              onClear={() => onSelectTool?.("chat")}
            />
          )}
          <div className="relative">
            <ComposerPrimitive.Unstable_TriggerPopover
              char="/"
              adapter={slash.adapter}
              className="absolute bottom-full left-2 z-50 mb-2 w-80 overflow-hidden rounded-xl border bg-popover p-1 text-popover-foreground shadow-md"
            >
              <ComposerPrimitive.Unstable_TriggerPopover.Action
                onExecute={slash.action.onExecute}
                removeOnExecute={slash.action.removeOnExecute}
              />
              <ComposerPrimitive.Unstable_TriggerPopoverItems>
                {(items) =>
                  items.map((item, index) => (
                    <ComposerPrimitive.Unstable_TriggerPopoverItem
                      key={item.id}
                      item={item}
                      index={index}
                      className="flex w-full cursor-pointer flex-col items-start gap-0.5 rounded-md px-2 py-1.5 text-left outline-none data-[highlighted]:bg-muted"
                    >
                      <span className="text-sm font-medium">{item.label}</span>
                      {item.description && (
                        <span className="text-xs text-muted-foreground">
                          {item.description}
                        </span>
                      )}
                    </ComposerPrimitive.Unstable_TriggerPopoverItem>
                  ))
                }
              </ComposerPrimitive.Unstable_TriggerPopoverItems>
            </ComposerPrimitive.Unstable_TriggerPopover>
            <ComposerPrimitive.Input
              placeholder={placeholder ?? "Send a message..."}
              className="mb-1 max-h-32 min-h-14 w-full resize-none bg-transparent px-4 pt-2 pb-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-0"
              rows={1}
              autoFocus
              aria-label="Message input"
            />
          </div>
          <ComposerAction
            tools={tools}
            activeTool={activeTool}
            onSelectTool={onSelectTool}
          />
        </ComposerPrimitive.AttachmentDropzone>
      </ComposerPrimitive.Unstable_TriggerPopoverRoot>
    </ComposerPrimitive.Root>
  );
}

// Pill above the input announcing the tool that will run on the next send.
// The X clears it back to plain chat.
function ActiveToolPill({
  tool,
  onClear,
}: {
  tool: ComposerTool;
  onClear: () => void;
}) {
  const Icon = tool.icon;
  return (
    <div className="mx-2 mb-1 flex">
      <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--accent-color)]/30 bg-[var(--accent-color)]/10 py-1 ps-2.5 pe-1.5 font-medium text-[var(--accent-color)] text-xs">
        {Icon && <Icon className="size-3.5" />}
        {tool.label}
        <button
          type="button"
          onClick={onClear}
          aria-label={`Turn off ${tool.label}`}
          className="flex size-4 items-center justify-center rounded-full text-[var(--accent-color)]/70 transition-colors hover:bg-[var(--accent-color)]/15 hover:text-[var(--accent-color)]"
        >
          <XIcon className="size-3" />
        </button>
      </span>
    </div>
  );
}

// Tools dropdown next to the add button. Each tool is a checkable toggle:
// selecting the active tool again clears it (back to chat).
function ToolsMenu({
  tools,
  activeTool,
  onSelectTool,
}: {
  tools: readonly ComposerTool[];
  activeTool?: string | null;
  onSelectTool?: (id: string) => void;
}) {
  if (tools.length === 0) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-8 gap-1.5 rounded-full px-2.5 text-muted-foreground text-xs hover:bg-muted-foreground/15 hover:text-foreground"
          aria-label="Tools"
        >
          <SlidersHorizontalIcon className="size-4 stroke-[1.5px]" />
          Tools
          <ChevronDownIcon className="size-3.5 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top">
        <DropdownMenuLabel>Tools</DropdownMenuLabel>
        {tools.map((tool) => {
          const Icon = tool.icon;
          const checked = tool.id === activeTool;
          return (
            <DropdownMenuCheckboxItem
              key={tool.id}
              checked={checked}
              // Selecting clears when already active, else activates the tool.
              onSelect={() => onSelectTool?.(checked ? "chat" : tool.id)}
            >
              {Icon && <Icon className="mt-0.5 size-4 text-muted-foreground" />}
              <span className="flex flex-col gap-0.5">
                <span className="font-medium">{tool.label}</span>
                <span className="text-muted-foreground text-xs">
                  {tool.description}
                </span>
              </span>
            </DropdownMenuCheckboxItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ComposerAction({
  tools = [],
  activeTool,
  onSelectTool,
}: {
  tools?: readonly ComposerTool[];
  activeTool?: string | null;
  onSelectTool?: (id: string) => void;
} = {}) {
  return (
    <div className="relative mx-2 mb-2 flex items-center justify-between">
      <div className="flex items-center gap-1">
        <ComposerAddAttachment />
        <ToolsMenu
          tools={tools}
          activeTool={activeTool}
          onSelectTool={onSelectTool}
        />
      </div>

      <AuiIf condition={(s) => !s.thread.isRunning}>
        <ComposerPrimitive.Send asChild>
          <TooltipIconButton
            tooltip="Send message"
            side="bottom"
            type="submit"
            variant="default"
            size="icon"
            className="size-8 rounded-full"
            style={{
              backgroundColor: "var(--accent-color)",
              color: "var(--accent-foreground)",
            }}
            aria-label="Send message"
          >
            <ArrowUpIcon className="size-4" />
          </TooltipIconButton>
        </ComposerPrimitive.Send>
      </AuiIf>

      <AuiIf condition={(s) => s.thread.isRunning}>
        <ComposerPrimitive.Cancel asChild>
          <Button
            type="button"
            variant="default"
            size="icon"
            className="size-8 rounded-full"
            style={{
              backgroundColor: "var(--accent-color)",
              color: "var(--accent-foreground)",
            }}
            aria-label="Stop generating"
          >
            <SquareIcon className="size-3 fill-current" />
          </Button>
        </ComposerPrimitive.Cancel>
      </AuiIf>
    </div>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root
      className="mx-auto grid w-full max-w-[var(--thread-max-width)] auto-rows-auto grid-cols-[minmax(72px,1fr)_auto] content-start gap-y-2 px-2 py-4 fade-in slide-in-from-bottom-1 animate-in duration-150"
      data-role="user"
    >
      <UserMessageAttachments />

      <div className="relative col-start-2 min-w-0">
        <div className="rounded-3xl bg-muted px-4 py-2.5 break-words text-foreground">
          <MessagePrimitive.Parts />
        </div>
        <div className="absolute top-1/2 left-0 -translate-x-full -translate-y-1/2 pr-2">
          <UserActionBar />
        </div>
      </div>

      <BranchPicker className="col-span-full col-start-1 row-start-3 -mr-1 justify-end" />
    </MessagePrimitive.Root>
  );
}

function UserActionBar() {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className="flex flex-col items-end"
    >
      <ActionBarPrimitive.Edit asChild>
        <TooltipIconButton tooltip="Edit" className="p-4">
          <PencilIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.Edit>
    </ActionBarPrimitive.Root>
  );
}

function EditComposer() {
  return (
    <MessagePrimitive.Root className="mx-auto flex w-full max-w-[var(--thread-max-width)] flex-col px-2 py-3">
      <ComposerPrimitive.Root className="ml-auto flex w-full max-w-[85%] flex-col rounded-3xl bg-muted">
        <ComposerPrimitive.Input
          className="min-h-14 w-full resize-none bg-transparent p-4 text-foreground text-sm outline-none"
          autoFocus
        />
        <div className="mx-3 mb-3 flex items-center gap-2 self-end">
          <ComposerPrimitive.Cancel asChild>
            <Button variant="ghost" size="sm">Cancel</Button>
          </ComposerPrimitive.Cancel>
          <ComposerPrimitive.Send asChild>
            <Button size="sm">Update</Button>
          </ComposerPrimitive.Send>
        </div>
      </ComposerPrimitive.Root>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root
      className="relative mx-auto w-full max-w-[var(--thread-max-width)] py-4 fade-in slide-in-from-bottom-1 animate-in duration-150"
      data-role="assistant"
    >
      <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <BotIcon className="size-4" />
      </div>
      <div className="break-words px-2 leading-relaxed text-foreground">
        <MessagePrimitive.GroupedParts
          groupBy={(part) =>
            part.type === "reasoning" ? ["group-reasoning"] : null
          }
        >
          {({ part, children }) => {
            switch (part.type) {
              case "group-reasoning": {
                const running = part.status.type === "running";
                return (
                  <ReasoningRoot defaultOpen={running}>
                    <ReasoningTrigger active={running} />
                    <ReasoningContent aria-busy={running}>
                      <ReasoningText>{children}</ReasoningText>
                    </ReasoningContent>
                  </ReasoningRoot>
                );
              }
              case "reasoning":
                return <MarkdownText />;
              case "text":
                return <MarkdownText />;
              case "tool-call": {
                if (part.toolName === "trackProgress") {
                  const parsed = safeParseSerializableProgressTracker(
                    part.result,
                  );
                  if (parsed) {
                    return (
                      <div className="my-2">
                        <ProgressTracker {...parsed} />
                      </div>
                    );
                  }
                }
                if (part.toolName === "verifyDocument") {
                  const props = checklistResultToProps(part.result);
                  if (props) {
                    return (
                      <div className="my-2">
                        <CitationChecklist {...props} />
                      </div>
                    );
                  }
                }
                return part.toolUI ?? <ToolFallback {...part} />;
              }
              default:
                return null;
            }
          }}
        </MessagePrimitive.GroupedParts>
        <MessageError />
        <AuiIf condition={(s) => s.thread.isRunning && s.message.content.length === 0}>
          <div className="flex items-center gap-2 text-muted-foreground">
            <LoaderIcon className="size-4 animate-spin" />
            <span className="text-sm">Thinking...</span>
          </div>
        </AuiIf>
      </div>

      <div className="mt-1 ml-2 flex min-h-6 items-center">
        <BranchPicker />
        <AssistantActionBar />
      </div>
      
    </MessagePrimitive.Root>
  );
}

function MessageError() {
  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root className="mt-2 rounded-md border border-destructive bg-destructive/10 p-3 text-destructive text-sm dark:bg-destructive/5 dark:text-red-200">
        <ErrorPrimitive.Message className="line-clamp-2" />
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
}

function AssistantActionBar() {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className="-ml-1 flex gap-1 text-muted-foreground"
    >
      <ActionBarPrimitive.Copy asChild>
        <TooltipIconButton tooltip="Copy">
          <AuiIf condition={(s) => s.message.isCopied}>
            <CheckIcon />
          </AuiIf>
          <AuiIf condition={(s) => !s.message.isCopied}>
            <CopyIcon />
          </AuiIf>
        </TooltipIconButton>
      </ActionBarPrimitive.Copy>
      <ActionBarPrimitive.ExportMarkdown asChild>
        <TooltipIconButton tooltip="Export as Markdown">
          <DownloadIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.ExportMarkdown>
      <ActionBarPrimitive.Reload asChild>
        <TooltipIconButton tooltip="Refresh">
          <RefreshCwIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.Reload>
      
      <ActionBarPrimitive.FeedbackPositive asChild>
        <TooltipIconButton tooltip="Good response">
          <ThumbsUpIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.FeedbackPositive>
      <ActionBarPrimitive.FeedbackNegative asChild>
        <TooltipIconButton tooltip="Bad response">
          <ThumbsDownIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.FeedbackNegative>
    </ActionBarPrimitive.Root>
  );
}

function BranchPicker({ className, ...rest }: { className?: string }) {
  return (
    <BranchPickerPrimitive.Root
      hideWhenSingleBranch
      className={cn("mr-2 -ml-2 inline-flex items-center text-xs text-muted-foreground", className)}
      {...rest}
    >
      <BranchPickerPrimitive.Previous asChild>
        <TooltipIconButton tooltip="Previous">
          <ChevronLeftIcon />
        </TooltipIconButton>
      </BranchPickerPrimitive.Previous>
      <span className="font-medium">
        <BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
      </span>
      <BranchPickerPrimitive.Next asChild>
        <TooltipIconButton tooltip="Next">
          <ChevronRightIcon />
        </TooltipIconButton>
      </BranchPickerPrimitive.Next>
    </BranchPickerPrimitive.Root>
  );
}