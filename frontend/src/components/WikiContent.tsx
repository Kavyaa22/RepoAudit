import { useRef } from "react";
import MermaidDiagram from "./MermaidDiagram";
import StructureCompare from "./StructureCompare";

interface Props {
  content: string;
  title: string;
  onNavigate?: (pageId: string) => void;
}

export default function WikiContent({ content, onNavigate }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    const anchor = target.closest("a");
    if (anchor) {
      const href = anchor.getAttribute("href");
      if (href && !href.startsWith("http://") && !href.startsWith("https://") && !href.startsWith("#")) {
        e.preventDefault();
        const cleanId = href.replace(/^\/+/, "").replace(/^project\/[^/]+\//, "");
        if (onNavigate) {
          onNavigate(cleanId);
        }
      }
    }
  };

  const parts = splitContent(content);

  return (
    <div ref={ref} onClick={handleClick} className="wiki-prose w-full py-6">
      {parts.map((part, i) => {
        if (part.type === "mermaid") {
          return (
            <div key={i} className="wiki-prose-narrow">
              <MermaidDiagram code={part.content} />
            </div>
          );
        }
        if (part.type === "structure-compare") {
          return (
            <div key={i} className="wiki-prose-wide px-6">
              <StructureCompare
                currentTree={part.current}
                suggestedTree={part.suggested}
              />
            </div>
          );
        }
        return (
          <div
            key={i}
            className="wiki-prose-narrow"
            dangerouslySetInnerHTML={{ __html: markdownToHtml(part.content) }}
          />
        );
      })}
    </div>
  );
}

interface TextPart {
  type: "text";
  content: string;
}

interface MermaidPart {
  type: "mermaid";
  content: string;
}

interface StructureComparePart {
  type: "structure-compare";
  current: string;
  suggested: string;
}

type ContentPart = TextPart | MermaidPart | StructureComparePart;

export function splitContent(md: string): ContentPart[] {
  if (!md) return [];

  // Pair structure-current + structure-suggested fences into one compare widget.
  const compareRegex =
    /```structure-current[ \t]*\r?\n([\s\S]*?)```\s*```structure-suggested[ \t]*\r?\n([\s\S]*?)```/gi;
  const withPlaceholders: { md: string; compares: { current: string; suggested: string }[] } = {
    md,
    compares: [],
  };
  withPlaceholders.md = md.replace(compareRegex, (_, current, suggested) => {
    const idx = withPlaceholders.compares.length;
    withPlaceholders.compares.push({
      current: String(current || "").trim(),
      suggested: String(suggested || "").trim(),
    });
    return `\n\n__STRUCTURE_COMPARE_${idx}__\n\n`;
  });

  // Interactive compare already shows added/removed folders — drop the markdown duplicate
  // (and the old From/To/Why table) so the page stays easy to read.
  if (withPlaceholders.compares.length) {
    withPlaceholders.md = stripSupersededStructureSections(withPlaceholders.md);
  }

  const parts: ContentPart[] = [];
  const regex = /```\s*mermaid[ \t]*\r?\n([\s\S]*?)(?:```|$)/gi;
  let lastIdx = 0;
  let match: RegExpExecArray | null;
  const source = withPlaceholders.md;

  while ((match = regex.exec(source)) !== null) {
    if (match.index > lastIdx) {
      pushTextWithCompares(parts, source.slice(lastIdx, match.index), withPlaceholders.compares);
    }
    const codeBody = normalizeMermaidCode(match[1] || "");
    if (codeBody) {
      parts.push({ type: "mermaid", content: codeBody });
    }
    lastIdx = match.index + match[0].length;
  }

  if (lastIdx < source.length) {
    pushTextWithCompares(parts, source.slice(lastIdx), withPlaceholders.compares);
  }

  return parts;
}

/** Drop markdown that the StructureCompare widget already presents. */
export function stripSupersededStructureSections(md: string): string {
  return md.replace(
    /^##\s+(?:What to change|Folder changes at a glance)\s*\r?\n[\s\S]*?(?=^##\s|\Z)/gim,
    "\n",
  );
}

function pushTextWithCompares(
  parts: ContentPart[],
  chunk: string,
  compares: { current: string; suggested: string }[],
) {
  if (!chunk) return;
  const split = chunk.split(/(__STRUCTURE_COMPARE_\d+__)/g);
  for (const piece of split) {
    if (!piece) continue;
    const m = piece.match(/^__STRUCTURE_COMPARE_(\d+)__$/);
    if (m) {
      const item = compares[Number(m[1])];
      if (item) {
        parts.push({
          type: "structure-compare",
          current: item.current,
          suggested: item.suggested,
        });
      }
      continue;
    }
    parts.push({ type: "text", content: piece });
  }
}

/** @deprecated use splitContent — kept for existing tests */
export function splitMermaid(md: string): { type: "text" | "mermaid"; content: string }[] {
  return splitContent(md).flatMap((part) => {
    if (part.type === "structure-compare") {
      return [
        {
          type: "text" as const,
          content: "Architecture comparison (open the wiki page for the interactive explorer).",
        },
      ];
    }
    return [part];
  });
}

export function normalizeMermaidCode(code: string): string {
  if (!code) return "";
  let cleaned = code.trim();

  cleaned = cleaned.replace(/\\r\\n/g, "\n").replace(/\\n/g, "\n").replace(/\\r/g, "");
  cleaned = cleaned.replace(/^```\s*mermaid\s*/i, "");
  cleaned = cleaned.replace(/```\s*$/i, "").trim();
  cleaned = cleaned.replace(/%%\{.*?\}%%/gs, "");
  cleaned = cleaned.replace(/^\s*classDef\b.*$/gm, "");
  cleaned = cleaned.replace(/^\s*style\b.*$/gm, "");
  cleaned = cleaned.replace(/(\b[A-Za-z0-9_]+)\[([^"\]\n\r]*[():\/&,\\-][^"\]\n\r]*)\]/g, '$1["$2"]');
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");

  return cleaned.trim();
}

function markdownToHtml(md: string): string {
  if (!md) return "";

  const codeBlocks: { lang: string; code: string }[] = [];
  let html = md.replace(/```(\w*)\r?\n([\s\S]*?)(?:```|$)/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push({ lang, code });
    return `\n\n__CODE_BLOCK_${idx}__\n\n`;
  });

  html = html.replace(/^### (.+)$/gm, '<h3 class="text-base font-bold text-slate-900 mt-6 mb-2">$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2 class="text-lg font-bold text-slate-900 mt-8 mb-3 pb-2 border-b border-slate-200">$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1 class="text-2xl font-extrabold text-slate-900 mb-4 pb-2 border-b border-slate-200">$1</h1>');
  html = html.replace(/^> (.+)$/gm, '<blockquote class="border-l-4 border-blue-500 pl-4 py-2 bg-blue-50/70 rounded-r-lg text-slate-700 text-sm my-3">$1</blockquote>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-slate-900">$1</strong>');
  html = html.replace(/`([^`]+)`/g, '<code class="bg-slate-100 px-1.5 py-0.5 rounded text-xs font-mono text-slate-800 border border-slate-200/60">$1</code>');
  html = html.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" class="text-blue-600 hover:text-blue-700 underline underline-offset-2">$1</a>');
  html = html.replace(/^- (.+)$/gm, '<li class="ml-4 list-disc text-sm text-slate-700 my-1 leading-relaxed">$1</li>');
  html = html.replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal text-sm text-slate-700 my-1 leading-relaxed">$1</li>');

  html = html.replace(/^\|(.+)\|$\n^\|[-| :]+\|$\n((?:^\|.+\|$\n?)+)/gm, (_, headerRow, bodyRows) => {
    const headers = headerRow
      .split("|")
      .filter((c: string) => c.trim() !== "")
      .map((c: string) => `<th class="px-3.5 py-2.5 bg-slate-50 font-bold text-left border border-slate-200 text-slate-700 text-xs uppercase tracking-wider">${c.trim()}</th>`)
      .join("");
    const rows = bodyRows
      .trim()
      .split("\n")
      .map((row: string) => {
        const cols = row
          .split("|")
          .filter((c: string) => c.trim() !== "")
          .map((c: string) => `<td class="px-3.5 py-2.5 border border-slate-200 text-xs text-slate-700 align-top break-words">${c.trim()}</td>`)
          .join("");
        return `<tr class="hover:bg-slate-50/60 transition-colors even:bg-slate-50/30">${cols}</tr>`;
      })
      .join("");
    return `<div class="generated-table-wrap my-5 rounded-xl border border-slate-200 bg-white overflow-x-auto shadow-2xs"><table class="generated-table w-full border-collapse text-xs my-0"><thead class="bg-slate-50 border-b border-slate-200"><tr>${headers}</tr></thead><tbody class="divide-y divide-slate-200">${rows}</tbody></table></div>`;
  });

  html = html.replace(/^(?!<[hblupt]|<li|<code|<pre|<div|<strong|<table|__CODE_BLOCK_\d+__)(.+)$/gm, '<p class="my-2 text-sm text-slate-700 leading-relaxed">$1</p>');

  codeBlocks.forEach(({ lang, code }, idx) => {
    const codeBlockHtml = `<pre class="bg-slate-900 text-slate-100 p-4 rounded-xl overflow-x-auto text-xs font-mono my-4 border border-slate-800"><code class="language-${lang || "text"} text-slate-100">${escapeHtml(code.trim())}</code></pre>`;
    html = html.replace(new RegExp(`<p[^>]*>\\s*__CODE_BLOCK_${idx}__\\s*</p>|__CODE_BLOCK_${idx}__`, "g"), codeBlockHtml);
  });

  return html;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
