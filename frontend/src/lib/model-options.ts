/** OpenRouter / LLM model options for user settings. */

export type ModelOption = {
  value: string;
  label: string;
  tier: "free" | "balanced" | "premium";
  description?: string;
};

export const GEMINI_FLASH_LITE = "openrouter/google/gemini-2.5-flash-lite";

export const MODEL_OPTIONS: ModelOption[] = [
  {
    value: "gemini-flash-lite",
    label: "Gemini 2.5 Flash Lite",
    tier: "balanced",
    description: "Default — fast wiki, structure, and security write-ups",
  },
  {
    value: "gemini-flash",
    label: "Gemini 2.5 Flash",
    tier: "balanced",
    description: "Same Gemini family as the default",
  },
  {
    value: "openrouter/deepseek/deepseek-chat",
    label: "DeepSeek Chat (Paid)",
    tier: "balanced",
    description: "Strong reasoning at low cost",
  },
  {
    value: "openrouter/anthropic/claude-sonnet-4",
    label: "Claude Sonnet 4 (Paid)",
    tier: "premium",
    description: "High-quality architecture analysis",
  },
  {
    value: "openrouter/openai/gpt-4o-mini",
    label: "GPT-4o Mini (Paid)",
    tier: "balanced",
    description: "Reliable daily driver",
  },
  {
    value: "nemotron-super",
    label: "Nemotron 3 Super (Free)",
    tier: "free",
    description: "Free fallback — slower and less reliable JSON",
  },
  {
    value: "laguna-xs",
    label: "Laguna XS 2.1 (Free)",
    tier: "free",
    description: "Fast free model for summaries & chat",
  },
  {
    value: "claude",
    label: "Claude Sonnet 4.6 (Direct)",
    tier: "premium",
    description: "Requires Anthropic-compatible routing",
  },
  {
    value: "deepseek",
    label: "DeepSeek V3 (Direct alias)",
    tier: "balanced",
    description: "Uses configured DeepSeek endpoint",
  },
];

export const DEFAULT_MODEL = "gemini-flash-lite";

const STALE_DEFAULTS = new Set([
  "nemotron-super",
  "nemotron",
  "flash",
]);

/** Map old cached defaults onto Gemini Flash Lite without wiping an intentional pick. */
export function normalizeStoredModel(model?: string): string {
  if (!model || STALE_DEFAULTS.has(model)) return DEFAULT_MODEL;
  return model;
}
