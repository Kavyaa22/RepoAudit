export default function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold text-slate-800">{title}</h1>
      <p className="text-sm text-slate-500">Scaffolded — implement this feature next.</p>
    </div>
  );
}
