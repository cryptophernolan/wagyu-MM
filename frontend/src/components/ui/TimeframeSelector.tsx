"use client";
interface Props {
  value: string;
  onChange: (v: string) => void;
  options?: string[];
}

const DEFAULT_OPTIONS = ["12h", "24h", "7d", "30d", "6m", "1y", "All"];

export function TimeframeSelector({ value, onChange, options = DEFAULT_OPTIONS }: Props): React.JSX.Element {
  return (
    <div className="flex gap-1">
      {options.map((opt) => (
        <button
          key={opt}
          onClick={() => onChange(opt.toLowerCase())}
          className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
            value === opt.toLowerCase() ? "bg-zinc-600 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
          }`}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}
