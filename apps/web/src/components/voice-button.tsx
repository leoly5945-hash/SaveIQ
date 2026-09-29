"use client";

import { useRef, useState, useSyncExternalStore } from "react";

// The Web Speech API isn't in TypeScript's DOM lib; this is the slice we use.
type RecognitionEvent = {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
};
type Recognition = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
};
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const noopSubscribe = () => () => {};

/**
 * Mic button for a search box: speech -> text, via the browser's own speech
 * recognition (Chrome/Edge/Safari; hidden where unsupported, e.g. Firefox).
 * `onText` gets the running transcript; `onFinal` the finished phrase.
 */
export function VoiceButton({
  onText,
  onFinal,
  onError,
}: {
  onText: (text: string) => void;
  onFinal: (text: string) => void;
  onError: (message: string) => void;
}) {
  const supported = useSyncExternalStore(
    noopSubscribe,
    () => recognitionCtor() !== null,
    () => false
  );
  const [listening, setListening] = useState(false);
  const active = useRef<Recognition | null>(null);

  if (!supported) return null;

  function toggle() {
    if (active.current) {
      active.current.stop();
      return;
    }
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const rec = new Ctor();
    rec.lang = "en-CA";
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    let finalText = "";
    rec.onresult = (event) => {
      let text = "";
      for (let i = 0; i < event.results.length; i += 1) {
        text += event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText = text;
      }
      onText(text.trim());
    };
    rec.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        onError("Microphone access is blocked. Allow it in your browser to search by voice.");
      } else if (event.error !== "no-speech" && event.error !== "aborted") {
        onError("We couldn't hear that. Try again, or type it instead.");
      }
    };
    rec.onend = () => {
      active.current = null;
      setListening(false);
      if (finalText.trim().length >= 2) onFinal(finalText.trim());
    };
    active.current = rec;
    setListening(true);
    rec.start();
  }

  return (
    <button
      aria-label={listening ? "Stop listening" : "Search by voice"}
      aria-pressed={listening}
      className={listening ? "pill-search-tool is-listening" : "pill-search-tool"}
      onClick={toggle}
      title={listening ? "Stop listening" : "Search by voice"}
      type="button"
    >
      <svg
        aria-hidden="true"
        fill="none"
        height="22"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="2.2"
        viewBox="0 0 24 24"
        width="22"
      >
        <rect height="12" rx="3.5" width="7" x="8.5" y="3" />
        <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
      </svg>
    </button>
  );
}
