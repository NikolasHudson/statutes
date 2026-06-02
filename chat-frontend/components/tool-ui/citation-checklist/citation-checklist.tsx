"use client";

// Citation checklist — the Verify Document counterpart to ProgressTracker.
// Where ProgressTracker shows sequential workflow steps, this lists every
// citation found in the document, each with its own green / yellow / red
// status chip and an expandable claim-vs-source detail. Card styling is kept
// deliberately close to ProgressTracker so the two surfaces feel like one app.

import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronRight,
  Loader2,
  PencilLine,
  SearchX,
  Timer,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import {
  type CitationFinding,
  type CitationStatus,
  type LanguageCheck,
  type VerifySummary,
  verdictLabel,
} from "@/lib/iowa-verify";
import { cn } from "@/lib/utils";

const STATUS_STYLE: Record<
  CitationStatus,
  { icon: typeof CheckCircle2; tone: string; chip: string; label: string }
> = {
  green: {
    icon: CheckCircle2,
    tone: "text-emerald-600 dark:text-emerald-500",
    chip: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
    label: "Verified",
  },
  yellow: {
    icon: AlertTriangle,
    tone: "text-amber-600 dark:text-amber-500",
    chip: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
    label: "Review",
  },
  red: {
    icon: XCircle,
    tone: "text-destructive",
    chip: "bg-destructive/10 text-destructive",
    label: "Problem",
  },
};

function formatElapsed(ms: number): string {
  const s = Math.round(Math.max(0, ms) / 100) / 10;
  if (s < 60) return `${s.toFixed(1)}s`;
  const whole = Math.floor(s);
  return `${Math.floor(whole / 60)}m ${whole % 60}s`;
}

function SummaryChips({ summary }: { summary: VerifySummary }) {
  const cells: { key: CitationStatus; n: number }[] = [
    { key: "green", n: summary.green },
    { key: "yellow", n: summary.yellow },
    { key: "red", n: summary.red },
  ];
  return (
    <div className="flex items-center gap-1.5">
      {cells.map(({ key, n }) => {
        const s = STATUS_STYLE[key];
        const Icon = s.icon;
        return (
          <span
            key={key}
            className={cn(
              "flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
              s.chip,
              n === 0 && "opacity-40",
            )}
          >
            <Icon className="size-3.5" />
            {n}
          </span>
        );
      })}
    </div>
  );
}

function VerdictBadge({ verdict }: { verdict: LanguageCheck["verdict"] }) {
  const bad = verdict === "not_found" || verdict === "contradicted";
  const soft =
    verdict === "fuzzy" || verdict === "partial" || verdict === "unverified";
  return (
    <span
      className={cn(
        "shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium",
        bad
          ? "bg-destructive/10 text-destructive"
          : soft
            ? "bg-amber-500/10 text-amber-700 dark:text-amber-400"
            : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
      )}
    >
      {verdictLabel(verdict)}
    </span>
  );
}

// Step 1 (form) indicator — distinct from the accuracy light. Shows the
// canonical citation, prominently when there's a correction to make.
function FormLine({ form }: { form: NonNullable<CitationFinding["form"]> }) {
  if (form.status === "ok") {
    // Nothing to fix — show the proper form only if it differs from what was
    // written (so we don't echo an already-correct cite back).
    if (!form.canonical || form.canonical === form.written) return null;
    return (
      <span className="text-muted-foreground/80 mt-0.5 flex items-center gap-1 text-xs">
        <Check className="size-3" />
        <span>
          Form: <span className="font-medium">{form.canonical}</span>
        </span>
      </span>
    );
  }
  const corrected = form.status === "corrected";
  const tone = corrected
    ? "text-amber-700 dark:text-amber-400"
    : "text-destructive";
  const Icon = corrected ? PencilLine : SearchX;
  return (
    <span className={cn("mt-0.5 flex items-center gap-1 text-xs", tone)}>
      <Icon className="size-3 shrink-0" />
      <span>
        {form.note}
        {form.canonical && (
          <>
            {" "}
            <span className="font-semibold">{form.canonical}</span>
          </>
        )}
      </span>
    </span>
  );
}

function FindingRow({ finding }: { finding: CitationFinding }) {
  const [open, setOpen] = useState(false);
  const s = STATUS_STYLE[finding.status];
  const Icon = s.icon;
  const hasDetail = finding.language_checks.length > 0 || !!finding.detail;

  return (
    <li className="border-border/60 border-b last:border-b-0">
      <button
        type="button"
        onClick={() => hasDetail && setOpen((v) => !v)}
        className={cn(
          "flex w-full items-start gap-3 px-2 py-2.5 text-left",
          hasDetail && "hover:bg-muted/40 rounded-lg",
        )}
        aria-expanded={hasDetail ? open : undefined}
      >
        <Icon className={cn("mt-0.5 size-5 shrink-0", s.tone)} />
        <div className="flex flex-1 flex-col gap-0.5">
          <div className="flex items-center gap-2">
            <code className="text-sm font-semibold">{finding.raw}</code>
            {finding.source_label && (
              <span className="text-muted-foreground text-xs">
                {finding.source_label}
              </span>
            )}
          </div>
          <span className="text-muted-foreground text-xs">
            {finding.detail}
          </span>
          {finding.form && <FormLine form={finding.form} />}
        </div>
        {hasDetail && (
          <ChevronRight
            className={cn(
              "text-muted-foreground mt-0.5 size-4 shrink-0 transition-transform",
              open && "rotate-90",
            )}
          />
        )}
      </button>

      {hasDetail && open && (
        <div className="flex flex-col gap-2 px-2 pb-3 pl-10">
          {finding.language_checks.map((c) => (
            <div
              key={`${c.kind}:${c.span[0]}:${c.verdict}`}
              className="flex flex-col gap-1"
            >
              <div className="flex items-center gap-2">
                <VerdictBadge verdict={c.verdict} />
                <span className="text-muted-foreground text-[11px] uppercase tracking-wide">
                  {c.kind}
                </span>
              </div>
              <p className="border-border bg-muted/30 rounded border-l-2 px-2 py-1 text-xs italic">
                “{c.claim_text}”
              </p>
              {c.source_excerpt && (
                <p className="text-muted-foreground px-2 text-xs">
                  <span className="font-medium">Source:</span>{" "}
                  {c.source_excerpt}
                </p>
              )}
            </div>
          ))}
          {finding.language_checks.length === 0 && (
            <p className="text-muted-foreground text-xs">{finding.detail}</p>
          )}
        </div>
      )}
    </li>
  );
}

export type CitationChecklistProps = {
  findings: CitationFinding[];
  total: number | null;
  summary: VerifySummary | null;
  elapsedMs: number;
  state: "running" | "done" | "error";
  errorMessage?: string;
  className?: string;
};

// Coerce a `verifyDocument` tool-call `result` (as emitted by the chat
// adapter) into checklist props, defensively. Returns null if the payload
// isn't a recognizable checklist so the caller can fall back.
export function checklistResultToProps(
  result: unknown,
): CitationChecklistProps | null {
  if (!result || typeof result !== "object") return null;
  const r = result as Record<string, unknown>;
  const state = r.state;
  if (state !== "running" && state !== "done" && state !== "error") return null;
  return {
    findings: Array.isArray(r.findings)
      ? (r.findings as CitationFinding[])
      : [],
    total: typeof r.total === "number" ? r.total : null,
    summary: (r.summary as VerifySummary | null) ?? null,
    elapsedMs: typeof r.elapsedTime === "number" ? r.elapsedTime : 0,
    state,
    errorMessage:
      typeof r.errorMessage === "string" ? r.errorMessage : undefined,
  };
}

export function CitationChecklist({
  findings,
  total,
  summary,
  elapsedMs,
  state,
  errorMessage,
  className,
}: CitationChecklistProps) {
  const remaining = total !== null ? Math.max(0, total - findings.length) : 0;
  const running = state === "running";

  return (
    <section
      className={cn("text-foreground flex w-full flex-col gap-3", className)}
      aria-live="polite"
      aria-busy={running}
    >
      <div className="bg-card flex w-full flex-col gap-3 rounded-2xl border p-5 shadow-xs">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {running && (
              <Loader2 className="text-primary size-4 motion-safe:animate-spin" />
            )}
            <span className="text-sm font-medium">
              {total === null
                ? "Reading document…"
                : running
                  ? `Verifying ${findings.length} of ${total} citation${total === 1 ? "" : "s"}`
                  : `${total} citation${total === 1 ? "" : "s"} checked`}
            </span>
          </div>
          <div className="flex items-center gap-3">
            {summary && <SummaryChips summary={summary} />}
            {elapsedMs > 0 && (
              <span className="text-muted-foreground flex items-center gap-1 font-mono text-xs">
                <Timer className="size-3.5" />
                {formatElapsed(elapsedMs)}
              </span>
            )}
          </div>
        </div>

        {state === "error" && (
          <p className="text-destructive text-sm">
            {errorMessage || "Verification failed."}
          </p>
        )}

        {total === 0 && state === "done" && (
          <p className="text-muted-foreground text-sm">
            No citations were found in this document.
          </p>
        )}

        {findings.length > 0 && (
          <ul className="m-0 flex list-none flex-col p-0">
            {findings.map((f) => (
              <FindingRow key={`${f.raw}-${f.span[0]}`} finding={f} />
            ))}
          </ul>
        )}

        {running && remaining > 0 && (
          <div className="text-muted-foreground flex items-center gap-2 px-2 text-xs">
            <Loader2 className="size-3.5 motion-safe:animate-spin" />
            {remaining} more to check…
          </div>
        )}
      </div>
    </section>
  );
}
