"use client";

// Verify Document page. Paste a brief/memo (or upload a text file), run the
// citation verifier, and watch every citation fill in green / yellow / red as
// the backend streams per-citation findings over NDJSON.

import { ArrowLeft, FileText, ShieldCheck, Upload, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { CitationChecklist } from "@/components/tool-ui/citation-checklist/citation-checklist";
import { Button } from "@/components/ui/button";
import {
  type CitationFinding,
  streamVerify,
  type VerifySummary,
} from "@/lib/iowa-verify";
import { cn } from "@/lib/utils";

type RunState = "idle" | "running" | "done" | "error";

// Extensions the backend can extract today (PDF/DOCX land with docling later).
const ACCEPT = ".txt,.md,.markdown,.text";

export default function VerifyPage() {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);

  const [findings, setFindings] = useState<CitationFinding[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [summary, setSummary] = useState<VerifySummary | null>(null);
  const [state, setState] = useState<RunState>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [elapsedMs, setElapsedMs] = useState(0);

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const canRun =
    state !== "running" && (file !== null || text.trim().length > 0);

  const run = useCallback(async () => {
    const input = file ? { file } : { text };
    if (!file && !text.trim()) return;

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setFindings([]);
    setTotal(null);
    setSummary(null);
    setErrorMessage("");
    setState("running");

    const startedAt = Date.now();
    setElapsedMs(0);
    const timer = setInterval(() => setElapsedMs(Date.now() - startedAt), 200);

    try {
      for await (const ev of streamVerify(input, ac.signal)) {
        switch (ev.type) {
          case "start":
            setTotal(ev.citations_total);
            break;
          case "citation_done":
            setFindings((prev) => [...prev, ev.finding]);
            break;
          case "summary":
            setSummary({
              total: ev.total,
              green: ev.green,
              yellow: ev.yellow,
              red: ev.red,
            });
            break;
          case "done":
            setState("done");
            break;
          case "error":
            setErrorMessage(ev.message);
            setState("error");
            break;
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setErrorMessage((e as Error).message ?? String(e));
        setState("error");
      }
    } finally {
      clearInterval(timer);
      setElapsedMs(Date.now() - startedAt);
      // The backend always closes with `done`/`error`; if the stream ended
      // without one (e.g. proxy cut it), resolve out of the running state.
      setState((s) => (s === "running" ? "done" : s));
    }
  }, [file, text]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setState("idle");
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setText("");
    setFile(null);
    setFindings([]);
    setTotal(null);
    setSummary(null);
    setErrorMessage("");
    setState("idle");
    setElapsedMs(0);
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  }, []);

  return (
    <div className="bg-background flex h-dvh w-full flex-col">
      <header className="flex h-16 shrink-0 items-center gap-3 border-b px-4">
        <Link
          href="/"
          className="text-muted-foreground hover:text-foreground flex items-center gap-1.5 text-sm"
        >
          <ArrowLeft className="size-4" />
          Chat
        </Link>
        <div className="bg-border h-4 w-px" />
        <div className="flex items-center gap-2">
          <ShieldCheck className="text-primary size-5" />
          <h1 className="text-sm font-semibold">Verify Document</h1>
        </div>
      </header>

      <div className="mx-auto w-full max-w-2xl flex-1 overflow-y-auto p-4 sm:p-6">
        <p className="text-muted-foreground mb-4 text-sm">
          Paste a brief or memo (or upload a text file). Every citation is
          checked two ways — that it resolves to a real provision, and that the
          language around it matches the actual source. Results:{" "}
          <span className="text-emerald-600 dark:text-emerald-500">green</span>{" "}
          verified,{" "}
          <span className="text-amber-600 dark:text-amber-500">yellow</span>{" "}
          needs review, <span className="text-destructive">red</span> problem.
        </p>

        {/* Input */}
        {!file ? (
          // biome-ignore lint/a11y/noStaticElementInteractions: file drop zone wraps a real textarea + file input; drag handlers are an enhancement, not the only path.
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cn(
              "flex flex-col gap-3 rounded-xl border p-3 transition-colors",
              dragging && "border-primary bg-primary/5",
            )}
          >
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste document text here…"
              disabled={state === "running"}
              rows={10}
              className={cn(
                "bg-background placeholder:text-muted-foreground w-full resize-y rounded-lg border px-3 py-2 text-sm",
                "focus-visible:ring-ring focus-visible:outline-none focus-visible:ring-2",
                "disabled:opacity-60",
              )}
            />
            <div className="flex items-center justify-between">
              <label className="text-muted-foreground hover:text-foreground flex cursor-pointer items-center gap-1.5 text-xs">
                <Upload className="size-3.5" />
                or upload a text file
                <input
                  type="file"
                  accept={ACCEPT}
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) setFile(f);
                  }}
                />
              </label>
              <span className="text-muted-foreground text-xs">
                {text.length.toLocaleString()} chars
              </span>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between rounded-xl border p-3">
            <div className="flex items-center gap-2 text-sm">
              <FileText className="text-primary size-5" />
              <span className="font-medium">{file.name}</span>
              <span className="text-muted-foreground text-xs">
                {(file.size / 1024).toFixed(0)} KB
              </span>
            </div>
            <button
              type="button"
              onClick={() => setFile(null)}
              className="text-muted-foreground hover:text-foreground"
              aria-label="Remove file"
            >
              <X className="size-4" />
            </button>
          </div>
        )}

        {/* Actions */}
        <div className="mt-3 flex items-center gap-2">
          {state === "running" ? (
            <Button variant="outline" onClick={cancel}>
              Cancel
            </Button>
          ) : (
            <Button onClick={run} disabled={!canRun}>
              <ShieldCheck className="size-4" />
              Verify citations
            </Button>
          )}
          {(state === "done" || state === "error") && (
            <Button variant="ghost" onClick={reset}>
              New document
            </Button>
          )}
        </div>

        {/* Results */}
        {state !== "idle" && (
          <div className="mt-6">
            <CitationChecklist
              findings={findings}
              total={total}
              summary={summary}
              elapsedMs={elapsedMs}
              state={state}
              errorMessage={errorMessage}
            />
          </div>
        )}
      </div>
    </div>
  );
}
