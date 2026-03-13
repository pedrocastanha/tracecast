import { appendFile, mkdir } from "fs/promises";
import { dirname } from "path";
import { Trace } from "../types";
import { BaseExporter } from "./base";

export interface JsonFileExporterOptions {
  
  includeFields?: string[];
  
  excludeFields?: string[];
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

export class JsonFileExporter implements BaseExporter {
  private readonly includeFields?: Set<string>;
  private readonly excludeFields?: Set<string>;

  constructor(
    private readonly path: string = "./traces.jsonl",
    options: JsonFileExporterOptions = {},
  ) {
    if (options.includeFields) this.includeFields = new Set(options.includeFields);
    else if (options.excludeFields) this.excludeFields = new Set(options.excludeFields);
  }

  async export(trace: Trace): Promise<void> {
    const dir = dirname(this.path);
    if (dir && dir !== ".") {
      await mkdir(dir, { recursive: true });
    }
    const raw: Record<string, unknown> = JSON.parse(JSON.stringify(trace));
    const doc = filterDoc(raw, this.includeFields, this.excludeFields);
    await appendFile(this.path, JSON.stringify(doc) + "\n", "utf-8");
  }
}
