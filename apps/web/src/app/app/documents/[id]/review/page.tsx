import type { Metadata } from "next";
import { Suspense } from "react";

import { ReviewPageView } from "./review-view";

export const metadata: Metadata = { title: "Review · DocFlow" };

export default function ReviewPage() {
  return (
    // The document id comes from the URL, which is only known at request time.
    <Suspense>
      <ReviewPageView />
    </Suspense>
  );
}
