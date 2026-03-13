type PriceEntry = { input: number; output: number };
type PriceTable = Record<string, PriceEntry>;
const PRICE_TABLE: PriceTable = {
  "gpt-5":             { input: 0.00125,  output: 0.01000 },
  "gpt-5.4":           { input: 0.00250,  output: 0.01500 },
  "gpt-4o":            { input: 0.00250,  output: 0.01000 },
  "gpt-4o-mini":       { input: 0.00015,  output: 0.00060 },
  "gpt-4-turbo":       { input: 0.01000,  output: 0.03000 },
  "gpt-4.1":           { input: 0.00200,  output: 0.00800 },
  "gpt-4.1-mini":      { input: 0.00040,  output: 0.00160 },
  "o3":                { input: 0.00200,  output: 0.00800 },
  "o4-mini":           { input: 0.00110,  output: 0.00440 },
  "claude-opus-4-6":   { input: 0.00500,  output: 0.02500 },
  "claude-sonnet-4-6": { input: 0.00300,  output: 0.01500 },
  "claude-haiku-4-5":  { input: 0.00100,  output: 0.00500 },
  "claude-opus-4-5":   { input: 0.00500,  output: 0.02500 },
  "claude-sonnet-4-5": { input: 0.00300,  output: 0.01500 },
  "claude-opus-4":     { input: 0.01500,  output: 0.07500 },
  "claude-sonnet-4":   { input: 0.00300,  output: 0.01500 },
  "claude-haiku-3-5":  { input: 0.00080,  output: 0.00400 },
  "gemini-3.1-pro":    { input: 0.00200,  output: 0.01200 },
  "gemini-3-flash":    { input: 0.00050,  output: 0.00300 },
  "gemini-2.5-flash":  { input: 0.00030,  output: 0.00250 },
  "gemini-2.5-pro":    { input: 0.00125,  output: 0.01000 },
  "gemini-2.0-flash":  { input: 0.00010,  output: 0.00040 },
  "llama-3.3-70b-versatile":                        { input: 0.00059, output: 0.00079 },
  "meta-llama/llama-4-scout-17b-16e-instruct":      { input: 0.00011, output: 0.00034 },
  "meta-llama/llama-4-maverick-17b-128e-instruct":  { input: 0.00020, output: 0.00060 },
  "llama-3.3-70b":     { input: 0.00059, output: 0.00079 },
  "llama-4-scout":     { input: 0.00011, output: 0.00034 },
  "llama-4-maverick":  { input: 0.00020, output: 0.00060 },
  "ollama/*":          { input: 0.0, output: 0.0 },
};

function prefixMatch(model: string, prices: PriceTable): PriceEntry | undefined {
  const provider = model.split("/")[0] + "/*";
  return prices[provider];
}

export function calculateCost(
  model: string,
  tokensIn: number,
  tokensOut: number,
  customPrices?: PriceTable,
): number {
  const prices = customPrices ? { ...PRICE_TABLE, ...customPrices } : PRICE_TABLE;
  const table = prices[model] ?? prefixMatch(model, prices);
  if (!table) return 0;
  return (tokensIn / 1000) * table.input + (tokensOut / 1000) * table.output;
}

export function getPriceTable(): Readonly<PriceTable> {
  return PRICE_TABLE;
}
