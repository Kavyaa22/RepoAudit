import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import mermaid from "mermaid";
import { normalizeMermaidCode } from "./WikiContent";

try {
  mermaid.initialize({
    startOnLoad: false,
    theme: "base",
    themeVariables: {
      darkMode: false,
      background: "#ffffff",
      mainBkg: "#ffffff",
      primaryColor: "#f0f9ff",       // bright light-sky fill
      primaryTextColor: "#0f172a",   // deep slate-900 high-contrast text
      primaryBorderColor: "#2563eb", // bold blue-600 border
      lineColor: "#334155",          // slate-700 crisp connector lines
      secondaryColor: "#ffffff",     // pure white
      secondaryTextColor: "#0f172a",
      secondaryBorderColor: "#2563eb",
      tertiaryColor: "#f8fafc",      // slate-50
      tertiaryTextColor: "#0f172a",
      tertiaryBorderColor: "#94a3b8",
      nodeBorder: "#2563eb",
      clusterBkg: "#ffffff",
      clusterBorder: "#94a3b8",
      titleColor: "#0f172a",
      edgeLabelBackground: "#ffffff",
      actorBkg: "#f0f9ff",
      actorBorder: "#2563eb",
      actorTextColor: "#0f172a",
      actorLineColor: "#334155",
      signalColor: "#1e293b",
      signalTextColor: "#0f172a",
      labelBoxBkgColor: "#ffffff",
      labelBoxBorderColor: "#cbd5e1",
      labelTextColor: "#0f172a",
      loopTextColor: "#0f172a",
      noteBorderColor: "#cbd5e1",
      noteBkgColor: "#fef9c3",
      noteTextColor: "#713f12",
      fontSize: "14px",
      fontFamily: "Inter, system-ui, -apple-system, sans-serif",
    },
    securityLevel: "loose",
    flowchart: { useMaxWidth: false, htmlLabels: true, curve: "basis" },
    sequence: { useMaxWidth: false, showSequenceNumbers: false },
  });
} catch {
  // Ignore re-initialization warnings
}

let mermaidId = 0;

interface Props {
  code: string;
}

function sanitizeNodeLabels(line: string): string {
  // Wrap unquoted node labels in double quotes if they contain parentheses, spaces, slashes, or special chars: e.g. ID[Text (1)] -> ID["Text (1)"]
  return line.replace(/(\b[\w-]+)\[([^"\]]+)\]/g, (match, nodeId, label) => {
    if (label.includes('"')) {
      const escaped = label.replace(/"/g, "'");
      return `${nodeId}["${escaped}"]`;
    }
    if (/[()/<>{}\s:#]/.test(label)) {
      return `${nodeId}["${label}"]`;
    }
    return match;
  });
}

function prepareDiagramCode(rawCode: string): string {
  let cleaned = normalizeMermaidCode(rawCode);
  if (!cleaned) return "";

  // Strip dark theme / style directives that cause unreadable text
  cleaned = cleaned.replace(/%%\{.*?\}%%/gs, "");
  cleaned = cleaned.replace(/^\s*classDef\b.*$/gm, "");
  cleaned = cleaned.replace(/^\s*style\b.*$/gm, "");
  // Collapse leftover blank lines
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n").trim();

  // Sanitize line by line for unescaped node labels
  const lines = cleaned.split("\n").map(sanitizeNodeLabels);
  cleaned = lines.join("\n");

  // If the code doesn't start with a known Mermaid header, check if it's node edges and prepend graph TD
  const lower = cleaned.toLowerCase();
  const knownHeaders = [
    "graph",
    "flowchart",
    "sequencediagram",
    "classdiagram",
    "statediagram",
    "erdiagram",
    "gantt",
    "pie",
    "gitgraph",
    "mindmap",
    "timeline",
    "quadrantchart",
    "architecture-beta",
  ];
  const hasKnownHeader = knownHeaders.some((h) => lower.startsWith(h) || lower.startsWith(`---`) || lower.includes(`\n${h}`));
  if (!hasKnownHeader && (cleaned.includes("-->") || cleaned.includes("->") || cleaned.includes("---"))) {
    cleaned = `graph TD\n${cleaned}`;
  }

  return cleaned;
}

export default function MermaidDiagram({ code }: Props) {
  const [error, setError] = useState("");
  const [svg, setSvg] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let isMounted = true;
    const cleanCode = prepareDiagramCode(code);
    if (!cleanCode) {
      setSvg("");
      setError("No diagram content available.");
      return;
    }

    const id = `mermaid-${Date.now()}-${++mermaidId}`;

    mermaid
      .render(id, cleanCode)
      .then(({ svg: next }) => {
        if (!isMounted) return;
        setSvg(next);
        setError("");
        // Clean up any stray error or temporary containers
        const stray = document.getElementById(`d${id}`) || document.getElementById(id);
        if (stray && stray.parentElement === document.body) {
          stray.remove();
        }
      })
      .catch((e) => {
        if (!isMounted) return;
        // Clean up any stray error container mermaid appends to body
        const stray = document.getElementById(`d${id}`) || document.getElementById(id);
        if (stray && stray.parentElement === document.body) {
          stray.remove();
        }

        // Try second pass with fallback graph TD if not tried
        if (!cleanCode.startsWith("graph TD") && !cleanCode.startsWith("flowchart")) {
          const fallbackCode = `graph TD\n${cleanCode.replace(/^[a-zA-Z\s]+\n/, "")}`;
          const fallbackId = `mermaid-fb-${Date.now()}-${++mermaidId}`;
          mermaid
            .render(fallbackId, fallbackCode)
            .then(({ svg: nextFb }) => {
              if (!isMounted) return;
              setSvg(nextFb);
              setError("");
              const strayFb = document.getElementById(`d${fallbackId}`) || document.getElementById(fallbackId);
              if (strayFb && strayFb.parentElement === document.body) strayFb.remove();
            })
            .catch(() => {
              if (!isMounted) return;
              setError(e instanceof Error ? e.message : "Diagram rendering error");
              setSvg("");
            });
        } else {
          setError(e instanceof Error ? e.message : "Diagram rendering error");
          setSvg("");
        }
      });

    return () => {
      isMounted = false;
      const stray = document.getElementById(`d${id}`) || document.getElementById(id);
      if (stray && stray.parentElement === document.body) {
        stray.remove();
      }
    };
  }, [code]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open]);

  if (error) {
    return (
      <div className="my-4 p-4 bg-amber-50/80 border border-amber-200 rounded-xl text-xs">
        <div className="flex items-center gap-2 text-amber-800 font-semibold mb-1">
          <svg className="w-4 h-4 text-amber-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span>Diagram format preview</span>
        </div>
        <p className="text-slate-600 mb-2 text-[11px]">{error}</p>
        <pre className="text-xs text-slate-700 bg-white p-3 rounded-lg border border-amber-200/60 overflow-x-auto font-mono max-h-48">
          {code}
        </pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="my-6 h-36 rounded-xl border border-slate-200 bg-slate-50/70 animate-pulse flex items-center justify-center text-xs text-slate-400">
        Rendering diagram…
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="group relative my-5 block w-full cursor-zoom-in rounded-xl border border-slate-200 bg-white text-left shadow-2xs hover:border-blue-300 hover:shadow-xs transition-all overflow-hidden"
        aria-label="Open diagram in a larger view"
      >
        <div
          ref={containerRef}
          className="max-h-[28rem] overflow-hidden p-5 flex items-center justify-center [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full [&_svg]:w-auto"
        >
          <div dangerouslySetInnerHTML={{ __html: svg }} />
        </div>
        <div className="absolute right-3 top-3 rounded-lg bg-slate-900/85 px-2.5 py-1 text-xs font-semibold text-white opacity-0 group-hover:opacity-100 transition-opacity">
          Click to expand · zoom & drag
        </div>
        <div className="border-t border-slate-100 px-4 py-2 bg-slate-50/60 flex items-center justify-between text-[11px] text-slate-500">
          <span>Click diagram to expand and explore in full resolution</span>
          <span className="text-blue-600 font-semibold group-hover:underline">Expand &rarr;</span>
        </div>
      </button>
      {open ? <DiagramLightbox svg={svg} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function DiagramLightbox({ svg, onClose }: { svg: string; onClose: () => void }) {
  const [scale, setScale] = useState(1);
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const dragging = useRef(false);
  const last = useRef({ x: 0, y: 0 });
  const stageRef = useRef<HTMLDivElement>(null);

  const zoomBy = useCallback((factor: number) => {
    setScale((current) => Math.min(8, Math.max(0.2, current * factor)));
  }, []);

  const reset = useCallback(() => {
    setScale(1);
    setTx(0);
    setTy(0);
  }, []);

  useEffect(() => {
    const node = stageRef.current;
    if (!node) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      zoomBy(event.deltaY > 0 ? 0.9 : 1.1);
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, [zoomBy]);

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    last.current = { x: event.clientX, y: event.clientY };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    const dx = event.clientX - last.current.x;
    const dy = event.clientY - last.current.y;
    last.current = { x: event.clientX, y: event.clientY };
    setTx((value) => value + dx);
    setTy((value) => value + dy);
  };

  const onPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    dragging.current = false;
    event.currentTarget.releasePointerCapture(event.pointerId);
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-slate-950/75 backdrop-blur-xs p-3 sm:p-6" role="dialog" aria-modal="true">
      <div className="mx-auto flex h-full w-full max-w-[96vw] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3 bg-white">
          <div>
            <p className="text-sm font-bold text-slate-800">Architecture Diagram</p>
            <p className="text-xs text-slate-500">Scroll to zoom · drag to pan · Esc to close</p>
          </div>
          <div className="flex items-center gap-1.5">
            <ToolbarButton onClick={() => zoomBy(0.85)} label="Zoom out">
              −
            </ToolbarButton>
            <span className="min-w-12 text-center text-xs font-semibold tabular-nums text-slate-600">
              {Math.round(scale * 100)}%
            </span>
            <ToolbarButton onClick={() => zoomBy(1.2)} label="Zoom in">
              +
            </ToolbarButton>
            <ToolbarButton onClick={reset} label="Reset view">
              Reset
            </ToolbarButton>
            <ToolbarButton onClick={onClose} label="Close">
              Close
            </ToolbarButton>
          </div>
        </div>
        <div
          ref={stageRef}
          className="relative min-h-0 flex-1 cursor-grab overflow-hidden bg-slate-50/50 active:cursor-grabbing"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          <div
            className="absolute left-1/2 top-1/2 origin-center [&_svg]:h-auto [&_svg]:max-w-none [&_svg]:w-auto"
            style={{ transform: `translate(calc(-50% + ${tx}px), calc(-50% + ${ty}px)) scale(${scale})` }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        </div>
      </div>
    </div>
  );
}

function ToolbarButton({
  onClick,
  label,
  children,
}: {
  onClick: () => void;
  label: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-2xs transition-colors cursor-pointer"
    >
      {children}
    </button>
  );
}

