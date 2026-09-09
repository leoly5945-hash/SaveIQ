"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A draggable bookmarklet. React refuses to render a `javascript:` href, so we
 * set it on the DOM node after mount. Also offers a copy button as a fallback.
 */
export function BookmarkletLink({ siteUrl }: { siteUrl: string }) {
  const ref = useRef<HTMLAnchorElement>(null);
  const [copied, setCopied] = useState(false);

  const code =
    `javascript:(function(){window.open('${siteUrl}/?url='` +
    `+encodeURIComponent(location.href),'_blank')})()`;

  useEffect(() => {
    if (ref.current) ref.current.setAttribute("href", code);
  }, [code]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard blocked — the drag target still works */
    }
  }

  return (
    <div className="bookmarklet">
      <a
        ref={ref}
        className="bookmarklet-drag"
        onClick={(e) => e.preventDefault()}
        href="#"
      >
        SaveIQ price check
      </a>
      <button className="bookmarklet-copy" type="button" onClick={() => void copy()}>
        {copied ? "Copied" : "Copy code"}
      </button>
    </div>
  );
}
