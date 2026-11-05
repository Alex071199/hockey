import { defineRailway, preserve, project, service } from "railway/iac";

export default defineRailway(() => {
  const hockeyLive = service("hockey-live", {
    replicas: { "europe-west4-drams3a": 1 },
    rootDirectory: "backend",
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    deploy: { healthcheckPath: "/api/health", healthcheckTimeout: 120 },
    env: { HIGHLIGHTLY_API_KEY: preserve(), HIGHLIGHTLY_API_KEYS: preserve(), ONHOCKEY_BASE_URL: preserve(), PRIME_PROXIES: preserve(), PRIME_PUBLIC_URL: preserve(), PUBLIC_API_URL: preserve(), SCHEDULER_ENABLED: preserve(), TELEGRAM_ADMIN_CHAT_ID: preserve(), TELEGRAM_BOT_TOKEN: preserve(), TURSO_AUTH_TOKEN: preserve(), TURSO_DATABASE_URL: preserve(), YOOMONEY_SECRET: preserve(), YOOMONEY_WALLET: preserve() },
  });

  return project("hockey-live", {
    resources: [hockeyLive],
  });
});
