import { defineRailway, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const hockeyLiveVolumeJPAp = volume("hockey-live-volume-jPAp", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "asia-southeast1-eqsg3a", sizeMB: 500 });
  const hockeyLive = service("hockey-live", {
    replicas: { "asia-southeast1-eqsg3a": 1 },
    volumeMounts: { "/data": hockeyLiveVolumeJPAp },
    env: { DATABASE_URL: preserve(), HIGHLIGHTLY_API_KEY: preserve(), HIGHLIGHTLY_API_KEYS: preserve(), ONHOCKEY_BASE_URL: preserve(), TELEGRAM_ADMIN_CHAT_ID: preserve(), TELEGRAM_BOT_TOKEN: preserve(), YOOMONEY_SECRET: preserve(), YOOMONEY_WALLET: preserve() },
  });

  return project("hockey-live", {
    resources: [hockeyLive, hockeyLiveVolumeJPAp],
  });
});
