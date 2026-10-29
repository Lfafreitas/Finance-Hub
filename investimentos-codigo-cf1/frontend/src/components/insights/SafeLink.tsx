/** Só abre link http(s); qualquer outra coisa vira texto. */
export function SafeLink({ url, children }: { url: string; children: string }) {
  if (!/^https?:\/\//i.test(url)) return <span>{children}</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="text-sky-400 underline-offset-2 hover:underline">
      {children}
    </a>
  );
}
