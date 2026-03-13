import { Trace } from "../types";
import { BaseExporter } from "./base";

export interface MongoExporterOptions {
  
  includeFields?: string[];
  
  excludeFields?: string[];
}


export class MongoExporter implements BaseExporter {
  private client: import("mongodb").MongoClient | null = null;
  private collectionPromise: Promise<import("mongodb").Collection> | null = null;

  private readonly includeFields?: Set<string>;
  private readonly excludeFields?: Set<string>;

  constructor(
    private readonly uri: string,
    private readonly dbName: string = "tracecast",
    private readonly collectionName: string = "traces",
    options: MongoExporterOptions = {},
  ) {
    if (options.includeFields) this.includeFields = new Set(options.includeFields);
    else if (options.excludeFields) this.excludeFields = new Set(options.excludeFields);
  }

  private async getCollection(): Promise<import("mongodb").Collection> {
    if (this.collectionPromise) return this.collectionPromise;

    this.collectionPromise = (async () => {
      let MongoClient: typeof import("mongodb").MongoClient;
      try {
        ({ MongoClient } = await import("mongodb"));
      } catch {
        throw new Error(
          "mongodb is required for MongoExporter. Install it with: npm install mongodb",
        );
      }
      this.client = new MongoClient(this.uri);
      await this.client.connect();
      return this.client.db(this.dbName).collection(this.collectionName);
    })();

    return this.collectionPromise;
  }

  async export(trace: Trace): Promise<void> {
    const col = await this.getCollection();
    const full: Record<string, unknown> = {
      ...traceToPlain(trace),
      exportedAt: new Date(),
    };
    const doc = filterDoc(full, this.includeFields, this.excludeFields);
    await col.insertOne(doc);
  }

  
  async close(): Promise<void> {
    if (this.client) {
      await this.client.close();
      this.client = null;
      this.collectionPromise = null;
    }
  }
}


function traceToPlain(trace: Trace): Record<string, unknown> {
  return {
    traceId:        trace.traceId,
    name:           trace.name,
    startedAt:      trace.startedAt,
    finishedAt:     trace.finishedAt ?? null,
    sessionId:      trace.sessionId ?? null,
    userId:         trace.userId ?? null,
    projectId:      trace.projectId ?? null,
    model:          trace.model ?? null,
    totalTokensIn:  trace.totalTokensIn,
    totalTokensOut: trace.totalTokensOut,
    totalTokens:    trace.totalTokens,
    costUsd:        trace.costUsd,
    latencyMs:      trace.latencyMs ?? null,
    toolsUsed:      trace.toolsUsed,
    spans:          trace.spans,
    metadata:       trace.metadata,
  };
}

function filterDoc(
  doc: Record<string, unknown>,
  include?: Set<string>,
  exclude?: Set<string>,
): Record<string, unknown> {
  if (include) {
    return Object.fromEntries(Object.entries(doc).filter(([k]) => include.has(k)));
  }
  if (exclude) {
    return Object.fromEntries(Object.entries(doc).filter(([k]) => !exclude.has(k)));
  }
  return doc;
}
