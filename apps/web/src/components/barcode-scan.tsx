"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

// The Barcode Detection API isn't in TypeScript's DOM lib yet.
type DetectedBarcode = { rawValue: string };
type Detector = { detect(source: HTMLVideoElement): Promise<DetectedBarcode[]> };
type DetectorCtor = new (options: { formats: string[] }) => Detector;

const RETAIL_FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e"];

function detectorCtor(): DetectorCtor | null {
  if (typeof window === "undefined") return null;
  const ctor = (window as unknown as { BarcodeDetector?: DetectorCtor }).BarcodeDetector;
  if (!ctor || !navigator.mediaDevices?.getUserMedia) return null;
  return ctor;
}

const noopSubscribe = () => () => {};

/**
 * Camera button that scans a product barcode (UPC / EAN) with the browser's
 * built-in detector — Chrome on Android and macOS today. Hidden where
 * unsupported; the box still accepts a typed barcode number there.
 */
export function BarcodeScanButton({ onCode }: { onCode: (code: string) => void }) {
  const supported = useSyncExternalStore(
    noopSubscribe,
    () => detectorCtor() !== null,
    () => false
  );
  const [open, setOpen] = useState(false);

  if (!supported) return null;

  return (
    <>
      <button
        aria-label="Scan a barcode"
        className="pill-search-tool"
        onClick={() => setOpen(true)}
        title="Scan a barcode"
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
          <path d="M3 8V5.5A2.5 2.5 0 0 1 5.5 3H8M16 3h2.5A2.5 2.5 0 0 1 21 5.5V8M21 16v2.5a2.5 2.5 0 0 1-2.5 2.5H16M8 21H5.5A2.5 2.5 0 0 1 3 18.5V16" />
          <path d="M7.5 8v8M11 8v8M14 8v8M17 8v8" />
        </svg>
      </button>
      {open ? (
        <ScannerDialog
          onClose={() => setOpen(false)}
          onCode={(code) => {
            setOpen(false);
            onCode(code);
          }}
        />
      ) : null}
    </>
  );
}

function ScannerDialog({
  onCode,
  onClose,
}: {
  onCode: (code: string) => void;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [problem, setProblem] = useState("");
  // Refs so a parent re-render (new inline callbacks) never restarts the camera.
  const onCodeRef = useRef(onCode);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCodeRef.current = onCode;
    onCloseRef.current = onClose;
  }, [onCode, onClose]);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stream: MediaStream | null = null;

    async function start() {
      const Ctor = detectorCtor();
      if (!Ctor) return;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: { facingMode: { ideal: "environment" } },
        });
      } catch {
        setProblem("Camera access is blocked. Allow it in your browser, or type the barcode number instead.");
        return;
      }
      if (stopped || !videoRef.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      const video = videoRef.current;
      video.srcObject = stream;
      await video.play().catch(() => undefined);
      const detector = new Ctor({ formats: RETAIL_FORMATS });

      const tick = async () => {
        if (stopped) return;
        try {
          const hits = await detector.detect(video);
          const hit = hits.find((b) => /^\d{8,14}$/.test(b.rawValue));
          if (hit) {
            stopped = true;
            onCodeRef.current(hit.rawValue);
            return;
          }
        } catch {
          // A frame that can't be read yet — keep scanning.
        }
        timer = setTimeout(() => void tick(), 250);
      };
      void tick();
    }

    void start();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      stream?.getTracks().forEach((t) => t.stop());
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  return (
    <div aria-label="Scan a barcode" aria-modal="true" className="scan-dialog" role="dialog">
      <div className="scan-panel">
        <p className="scan-title">Point your camera at the barcode</p>
        <div className="scan-view">
          <video muted playsInline ref={videoRef} />
          <span aria-hidden="true" className="scan-frame" />
        </div>
        {problem ? (
          <p className="scan-problem" role="alert">
            {problem}
          </p>
        ) : (
          <p className="scan-hint">
            Works with the UPC / EAN barcode on the box. Nothing is recorded —
            only the number is sent to look the product up.
          </p>
        )}
        <button className="scan-close" onClick={onClose} type="button">
          Cancel
        </button>
      </div>
    </div>
  );
}
