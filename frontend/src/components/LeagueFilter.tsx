"use client";

interface LeagueFilterProps {
  selected: string;
  onSelect: (league: string) => void;
}

export default function LeagueFilter({ selected, onSelect }: LeagueFilterProps) {
  const leagues = [
    { id: "all", label: "Все лиги", logo: null },
    { id: "KHL", label: "КХЛ", logo: "/KHL.svg" },
    { id: "VHL", label: "ВХЛ", logo: "/VHL.svg" },
    { id: "MHL", label: "МХЛ", logo: "/MHL.svg" },
  ];

  return (
    <div className="flex gap-1.5 sm:gap-2 overflow-x-auto pb-1 scrollbar-hide">
      {leagues.map((league) => (
        <button
          key={league.id}
          onClick={() => onSelect(league.id)}
          className={`flex items-center gap-1.5 sm:gap-2 px-3 sm:px-5 py-2 sm:py-2.5 rounded-lg text-xs sm:text-sm font-semibold transition-all duration-200 flex-shrink-0 ${
            selected === league.id
              ? "bg-hockey-accent text-white shadow-lg shadow-hockey-accent/20"
              : "bg-hockey-card border border-hockey-border text-hockey-text-secondary hover:text-white hover:border-hockey-border-light"
          }`}
        >
          {league.logo ? (
            <img src={league.logo} alt={league.label} className="h-3 sm:h-4 w-auto" />
          ) : (
            <span>{league.label}</span>
          )}
        </button>
      ))}
    </div>
  );
}
