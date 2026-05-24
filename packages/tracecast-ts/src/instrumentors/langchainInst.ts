import { BaseInstrumentor } from "./base";

/**
 * LangChain TS integration uses callbacks, not prototype patching.
 * Users attach TraceCastCallback to their LangChain chains manually.
 * This instrumentor is a stub that tracks registration state only.
 */
export class LangChainInstrumentor implements BaseInstrumentor {
  private _patched = false;

  patch(): void {
    this._patched = true;
  }

  unpatch(): void {
    this._patched = false;
  }

  isPatched(): boolean {
    return this._patched;
  }
}
