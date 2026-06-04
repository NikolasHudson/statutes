"use client";

// Edition comparison view: what changed between two published editions of a
// source. Thin shell around <EditionDiff/>; the corpus browser proper lives at
// /browse. A ?node=<id> query deep-links straight to one section's diff, and
// "Browse" returns to whichever section is currently open (via the corpus
// browser's #/<source>/<path> deep-link).

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeftIcon } from "lucide-react";

import { EditionDiff } from "@/components/edition-diff";
import { Button } from "@/components/ui/button";

const SOURCE = "iowa-code";

function Compare() {
  const params = useSearchParams();
  const rawNode = params.get("node");
  const initialNodeId =
    rawNode && /^\d+$/.test(rawNode) ? Number(rawNode) : undefined;

  // Seed from the ?path= we were linked with so "Browse" returns to the right
  // place even before the diff has loaded; then track the open section.
  const [sectionPath, setSectionPath] = useState<string | null>(
    params.get("path"),
  );
  const backHref = sectionPath
    ? `/browse#/${SOURCE}/${encodeURIComponent(sectionPath)}`
    : "/browse";

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex items-center gap-3 border-b px-4 py-2">
        <Button asChild variant="ghost" size="sm">
          <Link href={backHref}>
            <ArrowLeftIcon className="size-4" />
            {sectionPath ? "Back to section" : "Browse"}
          </Link>
        </Button>
        <h1 className="text-sm font-semibold">Iowa Code — edition changes</h1>
      </header>
      <div className="min-h-0 flex-1">
        <EditionDiff
          source={SOURCE}
          initialNodeId={initialNodeId}
          onSection={setSectionPath}
        />
      </div>
    </div>
  );
}

export default function CompareEditionsPage() {
  return (
    <Suspense fallback={null}>
      <Compare />
    </Suspense>
  );
}
