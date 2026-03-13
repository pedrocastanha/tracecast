import { Tracer } from "../src/core/tracer";
import { MongoExporter } from "../src/exporters/mongoExporter";
import { PostgresExporter } from "../src/exporters/postgresExporter";
import { Trace, Span, SpanType } from "../src/types";
import { randomUUID } from "crypto";

function makeTrace(overrides: Partial<Trace> = {}): Trace {
  return {
    traceId:       randomUUID(),
    name:          "test-trace",
    startedAt:     new Date(),
    finishedAt:    new Date(),
    totalTokensIn:  100,
    totalTokensOut: 50,
    totalTokens:    150,
    costUsd:        0.005,
    toolsUsed:      {},
    spans:          [],
    metadata:       {},
    ...overrides,
  };
}

describe("MongoExporter", () => {
  test("exporta trace para MongoDB (mock MongoClient)", async () => {
    const insertedDocs: unknown[] = [];

    const mockCollection = {
      insertOne: jest.fn(async (doc: unknown) => {
        insertedDocs.push(doc);
        return { insertedId: "fake-id" };
      }),
    };
    const mockDb     = { collection: jest.fn(() => mockCollection) };
    const mockClient = { connect: jest.fn(), db: jest.fn(() => mockDb), close: jest.fn() };

    jest.mock("mongodb", () => ({ MongoClient: jest.fn(() => mockClient) }), { virtual: true });

    const exporter = new MongoExporter("mongodb://localhost:27017", "tracecast_test", "traces");
    (exporter as any).collectionPromise = Promise.resolve(mockCollection);

    const trace = makeTrace({ userId: "u1", projectId: "p1" });
    await exporter.export(trace);

    expect(insertedDocs).toHaveLength(1);
    const doc = insertedDocs[0] as any;
    expect(doc.traceId).toBe(trace.traceId);
    expect(doc.userId).toBe("u1");
    expect(doc.projectId).toBe("p1");
    expect(doc.exportedAt).toBeInstanceOf(Date);
  });

  test("integra com Tracer via mock de collection", async () => {
    const insertedDocs: unknown[] = [];
    const mockCollection = {
      insertOne: jest.fn(async (doc: unknown) => {
        insertedDocs.push(doc);
      }),
    };

    const exporter = new MongoExporter("mongodb://localhost:27017");
    (exporter as any).collectionPromise = Promise.resolve(mockCollection);

    const tracer = new Tracer({ exporters: [exporter] });

    await tracer.trace("mongo-integration-test", async (trace) => {
      trace.spans.push({
        spanId:     randomUUID(),
        type:       SpanType.LLM,
        name:       "llm:gpt-4o",
        model:      "gpt-4o",
        startedAt:  new Date(),
        finishedAt: new Date(),
        tokensIn:   200,
        tokensOut:  100,
        costUsd:    0.0025 + 0.001,
      });
    }, { userId: "alice", sessionId: "sess-1" });

    expect(insertedDocs).toHaveLength(1);
    const doc = insertedDocs[0] as any;
    expect(doc.name).toBe("mongo-integration-test");
    expect(doc.userId).toBe("alice");
    expect(doc.sessionId).toBe("sess-1");
    expect(doc.totalTokens).toBe(300);
    expect(doc.costUsd).toBeGreaterThan(0);
    expect(doc.model).toBe("gpt-4o");
  });

  test("close() encerra a conexão", async () => {
    const mockClient = { connect: jest.fn(), db: jest.fn(), close: jest.fn() };
    const exporter = new MongoExporter("mongodb://localhost:27017");
    (exporter as any).client = mockClient;

    await exporter.close();

    expect(mockClient.close).toHaveBeenCalledTimes(1);
    expect((exporter as any).client).toBeNull();
  });

  test("exportedAt é um Date válido no documento inserido", async () => {
    const col = { insertOne: jest.fn(async () => {}) };
    const exporter = new MongoExporter("mongodb://host/db");
    (exporter as any).collectionPromise = Promise.resolve(col);
    const trace = makeTrace();
    await exporter.export(trace);
    const call = (col.insertOne as jest.Mock).mock.calls[0][0] as any;
    expect(call.exportedAt).toBeInstanceOf(Date);
  });
});

describe("PostgresExporter", () => {
  test("exporta trace para PostgreSQL (mock Pool)", async () => {
    const queries: { text: string; values: unknown[] }[] = [];

    const mockPool = {
      query: jest.fn(async (sql: string, values?: unknown[]) => {
        queries.push({ text: sql, values: values ?? [] });
        return { rows: [], rowCount: 0 };
      }),
      end: jest.fn(async () => {}),
    };

    const exporter = new PostgresExporter("postgresql://user:pass@localhost/db");
    (exporter as any).pool = mockPool;
    (exporter as any).initPromise = Promise.resolve();

    const trace = makeTrace({ userId: "u2", costUsd: 0.0123 });
    await exporter.export(trace);

    expect(mockPool.query).toHaveBeenCalledTimes(1);
    const [sql, values] = mockPool.query.mock.calls[0] as [string, string[]];
    expect(sql).toContain("INSERT INTO");
    expect(values[0]).toBe(trace.traceId);
    expect(values[3]).toBe("u2");
  });

  test("integra com Tracer via mock de Pool", async () => {
    const rows: unknown[][] = [];

    const mockPool = {
      query: jest.fn(async (_sql: string, values?: unknown[]) => {
        if (values) rows.push(values);
        return { rows: [], rowCount: 0 };
      }),
      end: jest.fn(async () => {}),
    };

    const exporter = new PostgresExporter("postgresql://user:pass@localhost/db", "llm_traces");
    (exporter as any).pool = mockPool;
    (exporter as any).initPromise = Promise.resolve();

    const tracer = new Tracer({ exporters: [exporter] });

    await tracer.trace("pg-integration-test", async (trace) => {
      trace.spans.push({
        spanId:     randomUUID(),
        type:       SpanType.LLM,
        name:       "llm:claude-sonnet-4-6",
        model:      "claude-sonnet-4-6",
        startedAt:  new Date(),
        finishedAt: new Date(),
        tokensIn:   500,
        tokensOut:  300,
        costUsd:    0.003,
      });
    }, { userId: "bob", projectId: "proj-pg" });

    expect(rows).toHaveLength(1);
    const values = rows[0] as string[];
    expect(values[0]).toMatch(/.{36}/);
    expect(values[3]).toBe("bob");
    expect(values[4]).toBe("proj-pg");
  });

  test("close() encerra o pool", async () => {
    const mockPool = {
      query: jest.fn(async () => ({ rows: [] })),
      end:   jest.fn(async () => {}),
    };
    const exporter = new PostgresExporter("postgresql://localhost/db");
    (exporter as any).pool = mockPool;
    (exporter as any).initPromise = Promise.resolve();

    await exporter.close();

    expect(mockPool.end).toHaveBeenCalledTimes(1);
    expect((exporter as any).pool).toBeNull();
  });

  test("upsert inclui ON CONFLICT para idempotência", async () => {
    const sqls: string[] = [];
    const mockPool = {
      query: jest.fn(async (sql: string) => {
        sqls.push(sql);
        return { rows: [] };
      }),
      end: jest.fn(async () => {}),
    };

    const exporter = new PostgresExporter("postgresql://localhost/db");
    (exporter as any).pool = mockPool;
    (exporter as any).initPromise = Promise.resolve();

    await exporter.export(makeTrace());
    expect(sqls[0]).toContain("ON CONFLICT");
    expect(sqls[0]).toContain("DO UPDATE");
  });
});
