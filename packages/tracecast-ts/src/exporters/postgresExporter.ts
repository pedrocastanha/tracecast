import { Trace } from "../types";
import { BaseExporter } from "./base";

const ALL_COLUMNS = [
  "trace_id",
  "name",
  "session_id",
  "user_id",
  "project_id",
  "model",
  "total_tokens_in",
  "total_tokens_out",
  "total_tokens",
  "cost_usd",
  "latency_ms",
  "tools_used",
  "spans",
  "metadata",
  "started_at",
  "finished_at",
  "exported_at",
] as const;

type Column = (typeof ALL_COLUMNS)[number];

const COLUMN_DEFS: Record<Column, string> = {
  trace_id:         "TEXT             NOT NULL",
  name:             "TEXT             NOT NULL",
  session_id:       "TEXT",
  user_id:          "TEXT",
  project_id:       "TEXT",
  model:            "TEXT",
  total_tokens_in:  "INTEGER          DEFAULT 0",
  total_tokens_out: "INTEGER          DEFAULT 0",
  total_tokens:     "INTEGER          DEFAULT 0",
  cost_usd:         "DOUBLE PRECISION DEFAULT 0",
  latency_ms:       "INTEGER",
  tools_used:       "JSONB            DEFAULT '{}'",
  spans:            "JSONB            DEFAULT '[]'",
  metadata:         "JSONB            DEFAULT '{}'",
  started_at:       "TIMESTAMPTZ      NOT NULL",
  finished_at:      "TIMESTAMPTZ",
  exported_at:      "TIMESTAMPTZ      NOT NULL",
};

const REQUIRED_COLUMNS = new Set<Column>(["trace_id", "started_at", "exported_at"]);

const JSONB_COLUMNS = new Set<Column>(["tools_used", "spans", "metadata"]);

function buildCreateSql(table: string, columns: Column[]): string {
  const colDefs = columns.map((c) => `  ${c} ${COLUMN_DEFS[c]}`);
  if (columns.includes("trace_id")) {
    colDefs.push(`  CONSTRAINT ${table}_trace_id_unique UNIQUE (trace_id)`);
  }
  return `CREATE TABLE IF NOT EXISTS ${table} (\n  id BIGSERIAL PRIMARY KEY,\n${colDefs.join(",\n")}\n);`;
}

function buildUpsertSql(table: string, columns: Column[]): { sql: string; orderedCols: Column[] } {
  const updateCols = columns.filter((c) => c !== "trace_id" && c !== "started_at");
  const placeholders = columns.map((_, i) => `$${i + 1}`).join(", ");
  const setClause = updateCols.map((c) => `  ${c} = EXCLUDED.${c}`).join(",\n");
  const sql = [
    `INSERT INTO ${table} (${columns.join(", ")})`,
    `VALUES (${placeholders})`,
    `ON CONFLICT (trace_id) DO UPDATE SET`,
    setClause + ";",
  ].join("\n");
  return { sql, orderedCols: columns };
}

export interface PostgresExporterOptions {
  
  includeFields?: string[];
  
  excludeFields?: string[];
}


export class PostgresExporter implements BaseExporter {
  private pool: import("pg").Pool | null = null;
  private initPromise: Promise<void> | null = null;

  private readonly columns: Column[];
  private readonly createSql: string;
  private readonly upsertSql: string;

  constructor(
    private readonly connectionString: string,
    private readonly tableName: string = "traces",
    options: PostgresExporterOptions = {},
  ) {
    if (options.includeFields) {
      const chosen = new Set<Column>([
        ...options.includeFields,
        ...REQUIRED_COLUMNS,
      ] as Column[]);
      this.columns = ALL_COLUMNS.filter((c) => chosen.has(c));
    } else if (options.excludeFields) {
      const excluded = new Set(
        options.excludeFields.filter((c) => !REQUIRED_COLUMNS.has(c as Column)),
      );
      this.columns = ALL_COLUMNS.filter((c) => !excluded.has(c));
    } else {
      this.columns = [...ALL_COLUMNS];
    }

    this.createSql = buildCreateSql(this.tableName, this.columns);
    const { sql } = buildUpsertSql(this.tableName, this.columns);
    this.upsertSql = sql;
  }

  private async init(): Promise<void> {
    if (this.initPromise) return this.initPromise;

    this.initPromise = (async () => {
      let Pool: typeof import("pg").Pool;
      try {
        ({ Pool } = await import("pg"));
      } catch {
        throw new Error(
          "pg is required for PostgresExporter. Install it with: npm install pg",
        );
      }
      this.pool = new Pool({ connectionString: this.connectionString });
      await this.pool.query(this.createSql);
    })();

    return this.initPromise;
  }

  async export(trace: Trace): Promise<void> {
    await this.init();

    const fullRow: Record<Column, unknown> = {
      trace_id:         trace.traceId,
      name:             trace.name,
      session_id:       trace.sessionId ?? null,
      user_id:          trace.userId ?? null,
      project_id:       trace.projectId ?? null,
      model:            trace.model ?? null,
      total_tokens_in:  trace.totalTokensIn,
      total_tokens_out: trace.totalTokensOut,
      total_tokens:     trace.totalTokens,
      cost_usd:         trace.costUsd,
      latency_ms:       trace.latencyMs ?? null,
      tools_used:       JSON.stringify(trace.toolsUsed),
      spans:            JSON.stringify(trace.spans),
      metadata:         JSON.stringify(trace.metadata),
      started_at:       trace.startedAt.toISOString(),
      finished_at:      trace.finishedAt?.toISOString() ?? null,
      exported_at:      new Date().toISOString(),
    };

    const values = this.columns.map((c) => fullRow[c]);
    await this.pool!.query(this.upsertSql, values);
  }

  
  async close(): Promise<void> {
    if (this.pool) {
      await this.pool.end();
      this.pool = null;
      this.initPromise = null;
    }
  }
}
