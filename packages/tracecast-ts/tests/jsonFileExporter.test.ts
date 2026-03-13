import { readFileSync, existsSync, rmSync } from "fs";
import { mkdtemp } from "fs/promises";
import { tmpdir } from "os";
import { join } from "path";
import { JsonFileExporter } from "../src/exporters/jsonFile";
import { Trace } from "../src/types";

const makeTrace = (id: string): Trace => ({
  traceId: id, name: "test", startedAt: new Date(), finishedAt: new Date(),
  totalTokensIn: 0, totalTokensOut: 0, totalTokens: 0,
  costUsd: 0, toolsUsed: {}, spans: [], metadata: {},
});

let tmpDir: string;

beforeEach(async () => {
  tmpDir = await mkdtemp(join(tmpdir(), "tracecast-test-"));
});

afterEach(() => {
  if (existsSync(tmpDir)) rmSync(tmpDir, { recursive: true });
});

test("escreve traces em jsonl (async)", async () => {
  const path = join(tmpDir, "traces.jsonl");
  const exporter = new JsonFileExporter(path);
  await exporter.export(makeTrace("t1"));
  await exporter.export(makeTrace("t2"));
  const lines = readFileSync(path, "utf-8").trim().split("\n");
  expect(lines).toHaveLength(2);
  expect(JSON.parse(lines[0]).traceId).toBe("t1");
  expect(JSON.parse(lines[1]).traceId).toBe("t2");
});

test("cria diretorio pai automaticamente", async () => {
  const path = join(tmpDir, "logs", "nested", "traces.jsonl");
  const exporter = new JsonFileExporter(path);
  await exporter.export(makeTrace("nested-1"));
  expect(existsSync(path)).toBe(true);
  const lines = readFileSync(path, "utf-8").trim().split("\n");
  expect(JSON.parse(lines[0]).traceId).toBe("nested-1");
});

test("append nao sobrescreve arquivo existente", async () => {
  const path = join(tmpDir, "traces.jsonl");
  const exporter = new JsonFileExporter(path);
  await exporter.export(makeTrace("a"));
  await exporter.export(makeTrace("b"));
  await exporter.export(makeTrace("c"));
  const lines = readFileSync(path, "utf-8").trim().split("\n");
  expect(lines).toHaveLength(3);
  expect(JSON.parse(lines[2]).traceId).toBe("c");
});

test("cada linha e JSON valido com campos do trace", async () => {
  const path = join(tmpDir, "traces.jsonl");
  const exporter = new JsonFileExporter(path);
  const trace = makeTrace("json-check");
  trace.metadata = { user: "alice", session: "s1" };
  await exporter.export(trace);
  const parsed = JSON.parse(readFileSync(path, "utf-8").trim());
  expect(parsed.traceId).toBe("json-check");
  expect(parsed.metadata.user).toBe("alice");
});
