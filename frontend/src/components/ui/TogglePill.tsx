"use client";

interface Props {
  label: string;
  description?: string;
  active: boolean;
  onToggle: () => void;
  loading?: boolean;
  error?: boolean;
  disabled?: boolean;
}

export function TogglePill({
  label,
  description,
  active,
  onToggle,
  loading = false,
  error = false,
  disabled = false,
}: Props): React.JSX.Element {
  const isDisabled = disabled || loading;

  let containerClass: string;
  let dotClass: string;
  let statusText: string;
  let statusTextClass: string;

  if (error) {
    containerClass = "bg-red-900/30 text-red-400 border border-red-700/50 hover:bg-red-900/40";
    dotClass = "bg-red-400 animate-pulse";
    statusText = "ERR";
    statusTextClass = "text-red-500";
  } else if (loading) {
    containerClass = "bg-amber-900/20 text-amber-400 border border-amber-700/30 cursor-wait";
    dotClass = "bg-amber-400 animate-pulse";
    statusText = "...";
    statusTextClass = "text-amber-500";
  } else if (active) {
    containerClass =
      "bg-green-600/15 text-green-300 border border-green-600/40 hover:bg-green-600/25 hover:border-green-500/50";
    dotClass = "bg-green-400";
    statusText = "ON";
    statusTextClass = "text-green-500";
  } else {
    containerClass =
      "bg-zinc-800 text-zinc-400 border border-zinc-700 hover:bg-zinc-700 hover:text-zinc-300";
    dotClass = "bg-zinc-600";
    statusText = "OFF";
    statusTextClass = "text-zinc-600";
  }

  return (
    <button
      onClick={onToggle}
      disabled={isDisabled}
      title={description}
      aria-pressed={active}
      aria-label={`${label}: ${active ? "on" : "off"}`}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold
        transition-all duration-150 select-none
        ${containerClass}
        ${isDisabled ? "cursor-not-allowed opacity-70" : "cursor-pointer"}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotClass}`} />
      <span>{label}</span>
      <span className={`text-[10px] font-mono font-bold ${statusTextClass}`}>{statusText}</span>
    </button>
  );
}
