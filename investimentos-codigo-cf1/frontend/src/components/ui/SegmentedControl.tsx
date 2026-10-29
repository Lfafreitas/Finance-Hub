/**
 * Controle segmentado do iOS: trilho cinza e uma "pílula" clara que
 * desliza até a opção escolhida. Cada opção continua sendo um botão com
 * `aria-pressed` (leitor de tela e teclado funcionam como antes).
 */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  size = "sm",
}: {
  options: { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
  label: string;
  size?: "sm" | "md";
}) {
  const index = Math.max(
    0,
    options.findIndex((o) => o.id === value),
  );
  const height = size === "md" ? "h-9 md:h-8" : "h-8 md:h-7";
  return (
    <div
      role="group"
      aria-label={label}
      className={`relative inline-grid rounded-[10px] bg-neutral-800/80 p-0.5 ${height}`}
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-0.5 left-0.5 rounded-[8px] bg-neutral-600/90 shadow-[0_1px_3px_rgba(0,0,0,0.35)] transition-transform duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)]"
        style={{
          width: `calc((100% - 4px) / ${options.length})`,
          transform: `translateX(${index * 100}%)`,
        }}
      />
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          aria-pressed={option.id === value}
          onClick={() => onChange(option.id)}
          className={`relative z-10 min-w-11 whitespace-nowrap px-3 text-[13px] font-medium transition-colors active:opacity-70 ${
            option.id === value ? "text-neutral-50" : "text-neutral-400 hover:text-neutral-200"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
