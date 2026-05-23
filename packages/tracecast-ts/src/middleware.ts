import { Tracer } from "./core/tracer";
import { IncomingMessage, ServerResponse } from "http";

export function traceCastMiddleware(
  tracer: Tracer,
  opts: { namePrefix?: string } = {},
) {
  return (req: IncomingMessage, res: ServerResponse, next: () => void) => {
    const method = req.method ?? "UNKNOWN";
    const path = req.url?.split("?")[0] ?? "/";
    const name = `${opts.namePrefix ?? ""}${method} ${path}`;

    tracer.trace(name, async () => {
      await new Promise<void>((resolve, reject) => {
        const originalEnd = res.end.bind(res);
        const writableEnd = function (this: ServerResponse, ...args: any[]) {
          resolve();
          return originalEnd(...args);
        };
        (res as any).end = writableEnd;
        try {
          next();
        } catch (err) {
          reject(err);
        }
      });
    }).catch(() => {});
  };
}
