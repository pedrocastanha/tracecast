export interface BaseInstrumentor {
  patch(): void;
  unpatch(): void;
  isPatched(): boolean;
}
