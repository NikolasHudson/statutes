"use client";

// Thin client shell for /cases/<decision node id>: fetch the case, then hand it
// to the three-pane <CaseConsole/>. Loading/error states show a minimal header
// so the user can navigate back while the (potentially large) opinion loads.

import { AlertCircleIcon, ArrowLeftIcon, Loader2Icon } from "lucide-react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { type CaseDetail, browseCase } from "@/lib/iowa-browse";
import { Button } from "@/components/ui/button";
import { CaseConsole } from "@/components/case-console";

export default function CasePage() {
  const params = useParams<{ id: string }>();
  // Strict integer id, mirroring app/browse/compare/page.tsx — a malformed
  // segment becomes NaN and is caught by the guard below.
  const nodeId = /^\d+$/.test(params.id) ? Number(params.id) : Number.NaN;

  const [data, setData] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!Number.isFinite(nodeId)) {
      setError("Invalid case id.");
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Clear the prior case so nothing stale shows while the next one loads
    // (cited-case links reuse this same route + component instance).
    setData(null);
    browseCase(nodeId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load case.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [nodeId]);

  if (data) return <CaseConsole data={data} />;

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex items-center gap-2 border-b px-3 py-2">
        <Button asChild variant="ghost" size="sm">
          <Link href="/browse">
            <ArrowLeftIcon className="size-4" />
            Browse
          </Link>
        </Button>
        <h1 className="font-semibold text-sm">Case</h1>
      </header>
      <div className="mx-auto w-full max-w-3xl px-4 py-6">
        {error ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-destructive text-sm">
            <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : loading ? (
          <div className="flex items-center gap-2 rounded-md border border-dashed p-4 text-muted-foreground text-sm">
            <Loader2Icon className="size-4 animate-spin" />
            Loading case…
          </div>
        ) : null}
      </div>
    </div>
  );
}
