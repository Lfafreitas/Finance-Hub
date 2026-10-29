import { isPrivate, setPrivate } from "../lib/privacy";

/** Olho aberto/fechado. O estado vem do App (que redesenha tudo ao trocar). */
export function PrivacyToggle({
  hidden,
  labelClass = "hidden sm:inline",
}: {
  hidden: boolean;
  /** Quando o texto aparece ao lado do olho (na barra lateral, só com ela aberta). */
  labelClass?: string;
}) {
  const label = hidden ? "Mostrar valores" : "Esconder valores";
  return (
    <button
      type="button"
      onClick={() => setPrivate(!isPrivate())}
      aria-pressed={hidden}
      title={label}
      aria-label={label}
      className={`ml-auto flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm transition-colors ${
        hidden ? "bg-neutral-800 text-neutral-50" : "text-neutral-400 hover:text-neutral-100"
      }`}
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        aria-hidden="true"
      >
        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
        <circle cx="12" cy="12" r="3" />
        {hidden && <path d="M4 4l16 16" />}
      </svg>
      <span className={labelClass}>{label}</span>
    </button>
  );
}
