/** Fixture / smoke-test repositories that should never appear in product UI. */

const DEMO_OWNER_REPO =
  /^(example\/)?demo(-[0-9a-f]{6,})?$/i;
const DEMO_DISPLAY = /^demo(-[0-9a-f]{6,})?$/i;
const DEMO_URL = /github\.com\/example\/demo/i;

function normalize(value: unknown): string {
  return String(value || "").trim();
}

export function isDemoRepository(
  ...values: Array<string | null | undefined>
): boolean {
  for (const value of values) {
    const text = normalize(value);
    if (!text) continue;
    if (DEMO_URL.test(text)) return true;
    if (DEMO_OWNER_REPO.test(text)) return true;
    if (DEMO_DISPLAY.test(text)) return true;
  }
  return false;
}

export function isDemoRecord(record: {
  name?: string | null;
  display_name?: string | null;
  project_name?: string | null;
  owner?: string | null;
  repository_name?: string | null;
  repository_url?: string | null;
  full_name?: string | null;
}): boolean {
  const owner = normalize(record.owner);
  const repo = normalize(record.repository_name);
  if (owner.toLowerCase() === "example" && DEMO_DISPLAY.test(repo)) {
    return true;
  }
  return isDemoRepository(
    record.full_name,
    record.name,
    record.display_name,
    record.project_name,
    record.repository_url,
    owner && repo ? `${owner}/${repo}` : "",
  );
}

export function rejectDemos<T extends Parameters<typeof isDemoRecord>[0]>(
  items: T[],
): T[] {
  return items.filter((item) => !isDemoRecord(item));
}
