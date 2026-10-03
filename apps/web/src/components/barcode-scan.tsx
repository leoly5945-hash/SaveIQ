"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

// The Barcode Detection API isn't in TypeScript's DOM lib yet.
type DetectedBarcode = { rawValue: string };
type Detector = { detect(source: HTMLVideoElement | ImageData): Promise<DetectedBarcode[]> };
type NativeDetectorCtor = {
  new (options: { formats: string[] }): Detector;
  getSupportedFormats?: () => Promise<string[]>;
};
// What the scan loop hands the detector each tick.
type Scanner = { detector: Detector; needsImageData: boolean };

const RETAIL_FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e"] as const;
// Longest side of the frame given to the bundled decoder.
const MAX_FRAME_SIDE = 1280;

function cameraAvailable(): boolean {
  return typeof window !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);
}

/**
 * The browser's own detector where it reads retail barcodes (Chrome on Android
 * and macOS); otherwise a bundled decoder (WebAssembly, loaded from this site
 * only when the scanner opens) — which is what Safari on iPhone and Firefox use.
 */
async function loadScanner(): Promise<Scanner> {
  const Native = (window as unknown as { BarcodeDetector?: NativeDetectorCtor }).BarcodeDetector;
  if (Native?.getSupportedFormats) {
    try {
      // macOS has no separate "upc_a": it reads UPC-A as EAN-13 with a leading 0.
      const supported = await Native.getSupportedFormats();
      const formats = RETAIL_FORMATS.filter((format) => supported.includes(format));
      if (formats.includes("ean_13")) {
        return { detector: new Native({ formats }), needsImageData: false };
      }
    } catch {
      // Fall through to the bundled decoder.
    }
  }
  const { BarcodeDetector, prepareZXingModule, ZXING_WASM_VERSION } = await import(
    "barcode-detector/ponyfill"
  );
  prepareZXingModule({
    overrides: {
      locateFile: (path: string, prefix: string) =>
        path.endsWith(".wasm")
          ? `/vendor/zxing_reader.wasm?v=${ZXING_WASM_VERSION}`
          : prefix + path,
    },
  });
  return {
    detector: new BarcodeDetector({ formats: [...RETAIL_FORMATS] }),
    needsImageData: true,
  };
}

function frameOf(video: HTMLVideoElement, canvas: HTMLCanvasElement): ImageData | null {
  const { videoWidth, videoHeight } = video;
  if (!videoWidth || !videoHeight) return null;
  const scale = Math.min(1, MAX_FRAME_SIDE / Math.max(videoWidth, videoHeight));
  canvas.width = Math.round(videoWidth * scale);
  canvas.height = Math.round(videoHeight * scale);
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

const noopSubscribe = () => () => {};

/**
 * Camera button that scans a product barcode (UPC / EAN). Hidden where the
 * browser has no camera access; the box still accepts a typed barcode number.
 */
export function BarcodeScanButton({ onCode }: { onCode: (code: string) => void }) {
  const supported = useSyncExternalStore(
    noopSubscribe,
    cameraAvailable,
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
      // Load the decoder while the shopper answers the camera prompt.
      const scannerReady = loadScanner().catch(() => null);
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: { ideal: "environment" },
            // A phone's default 640x480 is too coarse for a small barcode.
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
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
      const scanner = await scannerReady;
      if (stopped) return;
      if (!scanner) {
        setProblem("The scanner could not load. Type the barcode number instead.");
        return;
      }
      const canvas = document.createElement("canvas");

      const tick = async () => {
        if (stopped) return;
        try {
          const source = scanner.needsImageData ? frameOf(video, canvas) : video;
          const hits = source ? await scanner.detector.detect(source) : [];
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
          <video autoPlay muted playsInline ref={videoRef} />
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
