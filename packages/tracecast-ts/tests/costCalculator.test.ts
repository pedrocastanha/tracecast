import { calculateCost, getPriceTable } from "../src/core/costCalculator";

test.each([
  ["gpt-4o"],
  ["gpt-4o-mini"],
  ["gpt-4-turbo"],
  ["gpt-4.1"],
  ["gpt-4.1-mini"],
  ["o3"],
  ["o4-mini"],
  ["claude-opus-4-6"],
  ["claude-sonnet-4-6"],
  ["claude-haiku-4-5"],
  ["claude-opus-4"],
  ["claude-sonnet-4"],
  ["claude-haiku-3-5"],
  ["gemini-2.5-flash"],
  ["gemini-2.5-pro"],
  ["gemini-2.0-flash"],
  ["llama-3.3-70b"],
  ["llama-4-scout"],
  ["llama-4-maverick"],
])("calculateCost(%s) retorna valor > 0", (model) => {
  const cost = calculateCost(model, 1000, 500);
  expect(cost).toBeGreaterThan(0);
});

test("modelo desconhecido retorna 0", () => {
  expect(calculateCost("model-inexistente", 1000, 500)).toBe(0);
});

test("ollama/* retorna 0 (modelo local gratuito)", () => {
  expect(calculateCost("ollama/llama3", 1000, 500)).toBe(0);
  expect(calculateCost("ollama/mistral", 9999, 9999)).toBe(0);
});

test("calcula custo gpt-4o", () => {
  const cost = calculateCost("gpt-4o", 1000, 500);
  expect(cost).toBeCloseTo(0.0025 + 0.005, 9);
});

test("calcula custo gpt-4o-mini", () => {
  const cost = calculateCost("gpt-4o-mini", 1000, 1000);
  expect(cost).toBeCloseTo(0.00015 + 0.0006);
});

test("calcula custo claude-opus-4-6", () => {
  const cost = calculateCost("claude-opus-4-6", 1000, 1000);
  expect(cost).toBeCloseTo(0.005 + 0.025);
});

test("calcula custo gemini-2.5-flash", () => {
  const cost = calculateCost("gemini-2.5-flash", 1000, 1000);
  expect(cost).toBeCloseTo(0.00030 + 0.0025);
});

test("calcula custo llama-4-scout", () => {
  const cost = calculateCost("llama-4-scout", 1000, 1000);
  expect(cost).toBeCloseTo(0.00011 + 0.00034);
});

test("custom prices sobrescrevem tabela", () => {
  const custom = { "meu-modelo": { input: 1.0, output: 2.0 } };
  expect(calculateCost("meu-modelo", 1000, 1000, custom)).toBe(3.0);
});

test("custom prices nao quebram modelos builtin", () => {
  const custom = { "meu-modelo": { input: 1.0, output: 2.0 } };
  expect(calculateCost("gpt-4o", 1000, 0, custom)).toBeCloseTo(0.0025, 9);
  expect(calculateCost("meu-modelo", 1000, 0, custom)).toBeCloseTo(1.0, 9);
});

test("customPrices faz merge (nao replace) com tabela padrao", () => {
  const custom = { "modelo-novo": { input: 0.01, output: 0.02 } };
  expect(calculateCost("gpt-4o", 1000, 0, custom)).toBeGreaterThan(0);
  expect(calculateCost("modelo-novo", 1000, 0, custom)).toBeCloseTo(0.01);
});

test("claude-opus-4 (legacy) e mais caro que claude-opus-4-6 (atual)", () => {
  const legacy  = calculateCost("claude-opus-4",   1000, 1000);
  const current = calculateCost("claude-opus-4-6", 1000, 1000);
  expect(legacy).toBeGreaterThan(current);
});

test("claude-sonnet-4 e claude-sonnet-4-6 tem o mesmo preco", () => {
  const c1 = calculateCost("claude-sonnet-4",   1000, 1000);
  const c2 = calculateCost("claude-sonnet-4-6", 1000, 1000);
  expect(c1).toBeCloseTo(c2);
});

test("getPriceTable expoe tabela com todos os provedores principais", () => {
  const table = getPriceTable();
  expect(table["gpt-4o"]).toBeDefined();
  expect(table["claude-sonnet-4-6"]).toBeDefined();
  expect(table["gemini-2.5-flash"]).toBeDefined();
  expect(table["llama-4-scout"]).toBeDefined();
  expect(table["o4-mini"]).toBeDefined();
});
