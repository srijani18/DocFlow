import { z } from "zod";

// Public configuration, validated once at startup. NEXT_PUBLIC_* values must be read with
// literal `process.env.NAME` expressions so Next.js can inline them into the browser bundle.
const publicEnvSchema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z.url(),
});

export const env = publicEnvSchema.parse({
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
});
