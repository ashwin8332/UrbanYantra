import type { NextConfig } from "next";
import path from "path";
import { fileURLToPath } from "url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

/** HF Space backend — proxied via /api on Vercel to avoid CORS and env drift */
const HF_API_URL =
  process.env.HF_API_URL ?? "https://sleepingbeauty11-urbanyantra-api.hf.space";

const nextConfig: NextConfig = {
  // On Vercel, always call same-origin /api/* (rewritten to HF Space below)
  env: {
    NEXT_PUBLIC_API_BASE:
      process.env.NEXT_PUBLIC_API_BASE ??
      (process.env.VERCEL ? "/api" : "http://localhost:8000"),
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${HF_API_URL}/:path*`,
      },
    ];
  },
  ...(process.env.VERCEL
    ? {}
    : {
        turbopack: {
          root: frontendRoot,
        },
      }),
};

export default nextConfig;
