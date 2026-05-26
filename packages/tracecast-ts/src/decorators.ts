import { Tracer } from "./core/tracer";
import { Trace } from "./types";
import { getDefaultTracer, setDefaultTracer } from "./integrations/llm";

export { setDefaultTracer };

type TraceCastOpts = {
  name?: string;
  tracer?: Tracer;
  sessionId?: string;
  userId?: string;
  projectId?: string;
  metadata?: Record<string, unknown>;
};

export function traceCast<T extends (...args: any[]) => any>(
  fn: T,
  opts: TraceCastOpts = {},
): T {
  const name = opts.name ?? `${fn.name || "anonymous"}`;

  const wrapper = async function (this: any, ...args: any[]) {
    const tracer = opts.tracer ?? getDefaultTracer() ?? new Tracer();
    return tracer.trace(
      name,
      async (_trace: Trace) => fn.apply(this, args),
      {
        sessionId: opts.sessionId,
        userId: opts.userId,
        projectId: opts.projectId,
        metadata: opts.metadata,
      },
    );
  };

  return wrapper as unknown as T;
}
