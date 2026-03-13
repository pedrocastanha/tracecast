import { Trace } from "../types";
import { BaseExporter } from "./base";

export interface DictExporterOptions {
  
  onTrace?: (trace: Record<string, unknown>) => void;
  
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


export class DictExporter implements BaseExporter {
  
  public readonly traces: Record<string, unknown>[] = [];

  private readonly onTrace?: (trace: Record<string, unknown>) => void;
  private readonly includeFields?: Set<string>;
  private readonly excludeFields?: Set<string>;

  constructor(options: DictExporterOptions = {}) {
    this.onTrace = options.onTrace;
    if (options.includeFields) this.includeFields = new Set(options.includeFields);
    else if (options.excludeFields) this.excludeFields = new Set(options.excludeFields);
  }

  async export(trace: Trace): Promise<void> {
    const raw: Record<string, unknown> = JSON.parse(JSON.stringify(trace));
    const doc = filterDoc(raw, this.includeFields, this.excludeFields);
    if (this.onTrace) {
      this.onTrace(doc);
    } else {
      this.traces.push(doc);
    }
  }

  
  clear(): void {
    this.traces.length = 0;
  }
}
