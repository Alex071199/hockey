// Дата так, как её видит пользователь: YYYY-MM-DD в часовом поясе браузера.
// toISOString() даёт UTC-дату — из-за неё поздние матчи (04:00 по локали,
// 22:00 UTC предыдущего дня) ошибочно висели на «сегодня».
export function localDateKey(d: Date = new Date()): string {
  const p = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// Смещение локального пояса от UTC в минутах (UTC+6 → 360).
// Передаётся бэкенду, чтобы тот фильтровал расписание по полуночи клиента.
export function tzOffsetMinutes(): number {
  return -new Date().getTimezoneOffset();
}
