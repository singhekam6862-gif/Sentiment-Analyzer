import { Suspense } from "react";
import { AnalysisView } from "@/components/AnalysisView";

// The job id is only known at request time, so the view streams in behind Suspense.
export default function AnalysisPage() {
  return (
    <Suspense>
      <AnalysisView />
    </Suspense>
  );
}
