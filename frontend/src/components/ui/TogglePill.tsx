"use client";
interface Props {
  label: string;
  active: boolean;
  onToggle: () => void;
}

export function TogglePill({ label, active, onToggle }: Props): React.JSX.Element {
  return (
    <button
      onClick={onToggle}
      className={`px-3 py-1 rounded-full text-xs font-semibold transition-colors cursor-pointer ${
        active ? "bg-green-600 text-white" : "bg-zinc-700 text-zinc-400"
      }`}
    >
      {label}
    </button>
  );
}
