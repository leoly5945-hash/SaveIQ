import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const appDir = dirname(fileURLToPath(import.meta.url));

const nextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: join(appDir, "../.."),
  },
};

export default nextConfig;
