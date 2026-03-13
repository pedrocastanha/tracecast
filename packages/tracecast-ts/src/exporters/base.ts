import { Trace } from "../types";

export interface BaseExporter {
  export(trace: Trace): void | Promise<void>;
}
