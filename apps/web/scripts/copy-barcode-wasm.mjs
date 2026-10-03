// Copies the barcode decoder's WebAssembly file into public/ so the browser
// loads it from this site (the CSP allows connections to 'self' only), instead
// of the package's default CDN. Runs before `dev` and `build`.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
// zxing-wasm is a dependency of barcode-detector, so resolve it from there.
const fromDetector = createRequire(require.resolve("barcode-detector/ponyfill"));
const source = fromDetector.resolve("zxing-wasm/reader/zxing_reader.wasm");
const target = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "public",
  "vendor",
  "zxing_reader.wasm",
);

mkdirSync(dirname(target), { recursive: true });
copyFileSync(source, target);
console.log(`barcode decoder: ${source} -> ${target}`);
