export function parseMatchDate(iso: string): Date {
  if (!iso.includes("Z") && !iso.includes("+")) {
    return new Date(iso + "Z");
  }
  return new Date(iso);
}
