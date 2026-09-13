const TEAM_LOGOS: Record<string, string> = {
  "Автомобилист": "/logos/АВТОМОБИЛИСТ.png",
  "Авангард": "/logos/АВАНГАРД.png",
  "Адмирал": "/logos/АДМИРАЛ.png",
  "Ак Барс": "/logos/АК БАРС.png",
  "Амур": "/logos/АМУР.png",
  "Барыс": "/logos/БАРЫС.png",
  "Динамо М": "/logos/ДИНАМО М.png",
  "Динамо Минск": "/logos/ДИНАМО МН.png",
  "Динамо Мн": "/logos/ДИНАМО МН.png",
  "Шанхайские Драконы": "/logos/ДРАКОНЫ.png",
  "Драконы": "/logos/ДРАКОНЫ.png",
  "Лада": "/logos/ЛАДА.png",
  "Локомотив": "/logos/ЛОКОМОТИВ.png",
  "Металлург Мг": "/logos/МЕТАЛЛУРГ МГ.png",
  "Нефтехимик": "/logos/НЕФТЕХИМИК.png",
  "Салават Юлаев": "/logos/САЛАВАТ ЮЛАЕВ.png",
  "Северсталь": "/logos/СЕВЕРСТАЛЬ.png",
  "Сибирь": "/logos/СИБИРЬ.png",
  "СКА": "/logos/СКА.png",
  "Спартак": "/logos/СПАРТАК.png",
  "Трактор": "/logos/ТРАКТОР.png",
  "Торпедо": "/logos/ТОРПЕДО.png",
  "ХК Сочи": "/logos/ХК СОЧИ.png",
  "ЦСКА": "/logos/ЦСКА.png",
};

// Alias map for fallback lookup
const TEAM_ALIASES: Record<string, string> = {
  "Динамо Москва": "Динамо М",
  "Динамо Минск": "Динамо Мн",
  "Шанхай Драконы": "Шанхайские Драконы",
  "Shanghai Dragons": "Шанхайские Драконы",
  "Амур Хабаровск": "Амур",
  "Сочи": "ХК Сочи",
};

export function getTeamLogo(teamName: string): string | null {
  if (TEAM_LOGOS[teamName]) return TEAM_LOGOS[teamName];
  const alias = TEAM_ALIASES[teamName];
  if (alias && TEAM_LOGOS[alias]) return TEAM_LOGOS[alias];
  return null;
}
