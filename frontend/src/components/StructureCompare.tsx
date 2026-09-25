import { useEffect, useMemo, useState } from "react";

export type TreeNode = {
  name: string;
  path: string;
  isDir: boolean;
  children: TreeNode[];
};

const KNOWN_FILE_NAMES = new Set(
  [
    "dockerfile",
    "dockerfile.api",
    "dockerfile.web",
    "makefile",
    "gemfile",
    "rakefile",
    "procfile",
    "license",
    "licence",
    "readme",
    "changelog",
    "authors",
    "contributors",
    "copying",
    "nginx",
    "vagrantfile",
  ].map((s) => s.toLowerCase()),
);

function looksLikeFile(name: string): boolean {
  const base = name.replace(/\/$/, "");
  const lower = base.toLowerCase();
  if (KNOWN_FILE_NAMES.has(lower)) return true;
  if (lower.startsWith(".") && lower.includes(".")) return true; // .env.example
  if (lower.startsWith(".") && !lower.slice(1).includes("/")) return true; // .gitignore
  return /\.[a-z0-9]+$/i.test(base);
}

/** Parse ASCII tree or flat path list into a folder tree. */
export function parseStructureTree(raw: string): TreeNode[] {
  const text = (raw || "").trim();
  if (!text) return [];

  const paths = extractPaths(text);
  if (!paths.length) return [];

  const root: Record<string, any> = {};
  for (const path of paths) {
    const parts = path.replace(/\/$/, "").split("/").filter(Boolean);
    const markedDir = path.endsWith("/");
    let node = root;
    parts.forEach((part, idx) => {
      const isLast = idx === parts.length - 1;
      const asFile = isLast && looksLikeFile(part);
      const isDir = asFile ? false : !isLast || markedDir || !looksLikeFile(part);
      if (!node[part]) {
        node[part] = { __meta: { isDir }, __children: {} };
      } else if (isDir) {
        node[part].__meta.isDir = true;
      } else if (asFile) {
        node[part].__meta.isDir = false;
      }
      if (!isLast) {
        node[part].__meta.isDir = true;
        node = node[part].__children;
      }
    });
  }

  return objectToNodes(root, "");
}

function extractPaths(text: string): string[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const paths: string[] = [];
  const stack: string[] = [];

  for (const line of lines) {
    const stripped = line.trim();
    if (!stripped || stripped.startsWith("```") || stripped.startsWith("#")) continue;
    if (stripped.startsWith("Built with") || stripped.startsWith("**Migration")) continue;
    if (stripped.startsWith("Hierarchy:") || stripped.startsWith("### ")) continue;

    if (
      !stripped.includes("──") &&
      !stripped.startsWith("│") &&
      stripped.includes("/") &&
      !stripped.startsWith("- ")
    ) {
      const clean = stripped.replace(/^[*-]\s*/, "").replace(/`/g, "").split(/\s+[—–-]\s+/)[0].trim();
      if (clean.includes("/") || clean.endsWith("/")) {
        const body = clean.replace(/\/$/, "");
        const last = body.split("/").pop() || body;
        paths.push(looksLikeFile(last) ? body : `${body}/`);
      }
      continue;
    }

    const match = line.match(/^(.*?)([├└]──\s+|──\s+)(.+)$/);
    if (match) {
      const prefix = match[1] || "";
      let name = match[3].trim();
      const depth = Math.floor(prefix.replace(/\t/g, "    ").length / 4);
      while (stack.length > depth) stack.pop();
      const dirHint = name.endsWith("/");
      name = name.replace(/\/$/, "");
      if (name.startsWith("…") || name.startsWith("...")) continue;
      stack[depth] = name;
      const full = stack.slice(0, depth + 1).join("/");
      const treatAsDir = looksLikeFile(name) ? false : dirHint || !looksLikeFile(name);
      paths.push(treatAsDir ? `${full}/` : full);
      continue;
    }

    if (/^[A-Za-z0-9_.@-]+\/?$/.test(stripped)) {
      const name = stripped.replace(/\/$/, "");
      stack.length = 0;
      stack[0] = name;
      if (looksLikeFile(name)) {
        paths.push(name);
      } else {
        paths.push(`${name}/`);
      }
    }
  }

  return [...new Set(paths.filter(Boolean))];
}

function objectToNodes(obj: Record<string, any>, parentPath: string): TreeNode[] {
  return Object.keys(obj)
    .filter((k) => k !== "__meta" && k !== "__children")
    .sort((a, b) => {
      const aDir = !!obj[a].__meta?.isDir;
      const bDir = !!obj[b].__meta?.isDir;
      if (aDir !== bDir) return aDir ? -1 : 1;
      return a.localeCompare(b);
    })
    .map((name) => {
      const path = parentPath ? `${parentPath}/${name}` : name;
      const children = objectToNodes(obj[name].__children || {}, path);
      if (children.length > 0) {
        return { name, path, isDir: true, children };
      }
      const isDir = looksLikeFile(name) ? false : !!obj[name].__meta?.isDir;
      return { name, path, isDir, children };
    });
}

function collectDirPaths(nodes: TreeNode[]): Set<string> {
  const dirs = new Set<string>();
  const walk = (list: TreeNode[]) => {
    for (const n of list) {
      if (n.isDir) {
        dirs.add(n.path);
        walk(n.children);
      }
    }
  };
  walk(nodes);
  return dirs;
}

/** Keep highest-level folders only (drop children when a parent is already listed). */
export function compactFolderRoots(paths: Iterable<string>): string[] {
  const ordered = [...paths].sort((a, b) => a.split("/").length - b.split("/").length || a.length - b.length || a.localeCompare(b));
  const roots: string[] = [];
  for (const path of ordered) {
    if (roots.some((root) => path === root || path.startsWith(`${root}/`))) continue;
    roots.push(path);
  }
  return roots.sort((a, b) => a.localeCompare(b));
}

export function folderDelta(currentNodes: TreeNode[], suggestedNodes: TreeNode[]): {
  added: string[];
  removed: string[];
} {
  const current = collectDirPaths(currentNodes);
  const suggested = collectDirPaths(suggestedNodes);
  const added = new Set<string>();
  const removed = new Set<string>();
  for (const path of suggested) {
    if (!current.has(path)) added.add(path);
  }
  for (const path of current) {
    if (!suggested.has(path)) removed.add(path);
  }
  return {
    added: compactFolderRoots(added),
    removed: compactFolderRoots(removed),
  };
}

/** Full tree as indented text for clipboard (ignores collapse state). */
export function nodesToCopyText(nodes: TreeNode[]): string {
  const lines: string[] = [];
  const walk = (list: TreeNode[], depth: number) => {
    for (const n of list) {
      lines.push(`${"  ".repeat(depth)}${n.name}${n.isDir ? "/" : ""}`);
      if (n.isDir && n.children.length) walk(n.children, depth + 1);
    }
  };
  walk(nodes, 0);
  return lines.join("\n");
}

function TreeRow({
  node,
  depth,
  expanded,
  onToggle,
}: {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
}) {
  const isOpen = expanded.has(node.path);
  const hasKids = node.isDir && node.children.length > 0;

  return (
    <div>
      <button
        type="button"
        onClick={() => hasKids && onToggle(node.path)}
        className={`group w-full flex items-center gap-1.5 py-[3px] pr-2 text-left text-[12.5px] leading-5 rounded-sm ${
          hasKids ? "cursor-pointer hover:bg-white/10" : "cursor-default"
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        title={node.path}
      >
        <span
          className={`inline-flex w-4 h-4 shrink-0 items-center justify-center text-slate-400 ${
            hasKids ? "group-hover:text-slate-200" : "opacity-0"
          }`}
          aria-hidden
        >
          <svg
            viewBox="0 0 16 16"
            className={`w-3 h-3 transition-transform duration-150 ${isOpen ? "rotate-90" : ""}`}
            fill="currentColor"
          >
            <path d="M6 3.5l5 4.5-5 4.5V3.5z" />
          </svg>
        </span>
        <span
          className={`shrink-0 w-4 h-4 ${node.isDir ? "text-slate-300" : "text-slate-500"}`}
          aria-hidden
        >
          {node.isDir ? (
            <svg viewBox="0 0 16 16" className="w-4 h-4" fill="currentColor">
              <path d="M1.5 3.5A1.5 1.5 0 0 1 3 2h3.172a1.5 1.5 0 0 1 1.06.44L8.5 3.72H13A1.5 1.5 0 0 1 14.5 5.22v6.28A1.5 1.5 0 0 1 13 13H3A1.5 1.5 0 0 1 1.5 11.5v-8z" />
            </svg>
          ) : (
            <svg viewBox="0 0 16 16" className="w-4 h-4" fill="currentColor">
              <path d="M4 1.5A1.5 1.5 0 0 0 2.5 3v10A1.5 1.5 0 0 0 4 14.5h8a1.5 1.5 0 0 0 1.5-1.5V5.56a1.5 1.5 0 0 0-.44-1.06L10 1.94A1.5 1.5 0 0 0 8.94 1.5H4zm5 .5v2.5H12L9 2z" />
            </svg>
          )}
        </span>
        <span
          className={`min-w-0 break-all ${
            node.isDir ? "font-semibold text-slate-100" : "font-normal text-slate-300"
          }`}
        >
          {node.name}
        </span>
      </button>
      {hasKids && isOpen &&
        node.children.map((child) => (
          <TreeRow
            key={child.path}
            node={child}
            depth={depth + 1}
            expanded={expanded}
            onToggle={onToggle}
          />
        ))}
    </div>
  );
}

function defaultExpanded(nodes: TreeNode[], maxDepth = 0): Set<string> {
  const set = new Set<string>();
  const walk = (list: TreeNode[], depth: number) => {
    for (const n of list) {
      if (n.isDir && depth <= maxDepth) {
        set.add(n.path);
        walk(n.children, depth + 1);
      }
    }
  };
  walk(nodes, 0);
  return set;
}

function CopyArchitectureButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!text.trim()) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleCopy()}
      disabled={!text.trim()}
      className="ml-auto text-[11px] font-semibold text-slate-400 hover:text-slate-100 px-2 py-1 rounded-md hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

export function StructureTreeExplorer({
  treeText,
  emptyLabel = "No folder tree available.",
  /** Folders deeper than this start collapsed (0 = only roots open). */
  initialExpandDepth = 1,
}: {
  treeText: string;
  emptyLabel?: string;
  initialExpandDepth?: number;
}) {
  const nodes = useMemo(() => parseStructureTree(treeText), [treeText]);
  const copyText = useMemo(() => nodesToCopyText(nodes) || treeText.trim(), [nodes, treeText]);
  // Default: open top + first level; sub-sub folders (depth >= 2) stay collapsed.
  const [expanded, setExpanded] = useState<Set<string>>(() =>
    defaultExpanded(nodes, initialExpandDepth),
  );

  useEffect(() => {
    setExpanded(defaultExpanded(nodes, initialExpandDepth));
  }, [treeText, nodes, initialExpandDepth]);

  const toggle = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const expandAll = () => {
    const all = new Set<string>();
    const walk = (list: TreeNode[]) => {
      for (const n of list) {
        if (n.isDir) {
          all.add(n.path);
          walk(n.children);
        }
      }
    };
    walk(nodes);
    setExpanded(all);
  };

  const collapseAll = () => setExpanded(new Set());

  if (!nodes.length) {
    return (
      <p className="text-xs text-slate-400 px-3 py-6 italic font-mono">{emptyLabel}</p>
    );
  }

  return (
    <div className="flex flex-col min-h-0 rounded-xl overflow-hidden border border-slate-800 bg-slate-900">
      <div className="flex items-center gap-1 px-2 py-1.5 border-b border-slate-700/80 shrink-0 bg-slate-950/60">
        <button
          type="button"
          onClick={expandAll}
          className="text-[11px] font-semibold text-slate-400 hover:text-slate-100 px-2 py-1 rounded-md hover:bg-white/10"
        >
          Expand all
        </button>
        <button
          type="button"
          onClick={collapseAll}
          className="text-[11px] font-semibold text-slate-400 hover:text-slate-100 px-2 py-1 rounded-md hover:bg-white/10"
        >
          Collapse all
        </button>
        <CopyArchitectureButton text={copyText} />
      </div>
      <div className="py-2 px-1 font-mono text-[12.5px]">
        {nodes.map((node) => (
          <TreeRow
            key={node.path}
            node={node}
            depth={0}
            expanded={expanded}
            onToggle={toggle}
          />
        ))}
      </div>
    </div>
  );
}

function FolderDeltaSummary({
  currentTree,
  suggestedTree,
}: {
  currentTree: string;
  suggestedTree: string;
}) {
  const { added, removed } = useMemo(() => {
    const currentNodes = parseStructureTree(currentTree);
    const suggestedNodes = parseStructureTree(suggestedTree);
    return folderDelta(currentNodes, suggestedNodes);
  }, [currentTree, suggestedTree]);

  if (!added.length && !removed.length) {
    return (
      <section className="rounded-xl border border-slate-200 bg-slate-50/80 px-4 py-4">
        <h3 className="text-base font-bold text-slate-900">Folder changes at a glance</h3>
        <p className="text-sm text-slate-600 mt-2 leading-relaxed">
          The suggested layout keeps the same folders — nothing major to add or remove at a glance.
        </p>
      </section>
    );
  }

  return (
    <section>
      <div className="mb-3">
        <h3 className="text-base font-bold text-slate-900">Folder changes at a glance</h3>
        <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
          What the suggestion introduces or stops using. Nested folders under each path are included.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/40 px-4 py-3">
          <h4 className="text-sm font-bold text-emerald-900">New folders we&apos;d create</h4>
          {added.length ? (
            <ul className="mt-2 space-y-1.5">
              {added.map((path) => (
                <li key={path} className="text-sm text-slate-700 font-mono break-all">
                  <span className="text-emerald-700 font-sans font-semibold mr-1.5">+</span>
                  {path}/
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-slate-600">
              None — the suggestion reuses today&apos;s folder names.
            </p>
          )}
        </div>
        <div className="rounded-xl border border-rose-200/80 bg-rose-50/40 px-4 py-3">
          <h4 className="text-sm font-bold text-rose-900">Folders we can leave behind</h4>
          {removed.length ? (
            <ul className="mt-2 space-y-1.5">
              {removed.map((path) => (
                <li key={path} className="text-sm text-slate-700 font-mono break-all">
                  <span className="text-rose-700 font-sans font-semibold mr-1.5">−</span>
                  {path}/
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-slate-600">
              None — today&apos;s folders still appear in the suggestion.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

export default function StructureCompare({
  currentTree,
  suggestedTree,
}: {
  currentTree: string;
  suggestedTree: string;
}) {
  return (
    <div className="my-6 space-y-8">
      <section>
        <div className="mb-3">
          <h3 className="text-base font-bold text-slate-900">Current architecture</h3>
          <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
            How the repository looks today. Sub-folders start collapsed — use the arrows to open what you need.
          </p>
        </div>
        <StructureTreeExplorer
          treeText={currentTree}
          emptyLabel="Current structure was not captured."
          initialExpandDepth={1}
        />
      </section>

      <section>
        <div className="mb-3">
          <h3 className="text-base font-bold text-slate-900">Suggested architecture</h3>
          <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
            Target Feature → Action layout. Same collapsible tree — expand only the branches you want to review.
          </p>
        </div>
        <StructureTreeExplorer
          treeText={suggestedTree}
          emptyLabel="No suggested structure yet."
          initialExpandDepth={1}
        />
      </section>

      <FolderDeltaSummary currentTree={currentTree} suggestedTree={suggestedTree} />
    </div>
  );
}
