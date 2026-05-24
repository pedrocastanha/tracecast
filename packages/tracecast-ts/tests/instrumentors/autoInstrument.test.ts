import { autoInstrument, _resetInstrument, _registerInstrumentor } from "../../src/instrument";
import { BaseInstrumentor } from "../../src/instrumentors/base";

class FakeInstrumentor implements BaseInstrumentor {
  patched = false;
  patch() { this.patched = true; }
  unpatch() { this.patched = false; }
  isPatched() { return this.patched; }
}

describe("autoInstrument", () => {
  afterEach(() => _resetInstrument());

  it("calls patch on registered instrumentors", () => {
    const fake = new FakeInstrumentor();
    _registerInstrumentor("fake", fake);
    autoInstrument();
    expect(fake.isPatched()).toBe(true);
  });

  it("is idempotent — calling twice does not double-patch", () => {
    const fake = new FakeInstrumentor();
    _registerInstrumentor("fake", fake);
    autoInstrument();
    autoInstrument();
    expect(fake.isPatched()).toBe(true);
  });

  it("skips instrumentors that throw on patch", () => {
    const bad: BaseInstrumentor = {
      patch() { throw new Error("no module"); },
      unpatch() {},
      isPatched() { return false; },
    };
    _registerInstrumentor("bad", bad);
    expect(() => autoInstrument()).not.toThrow();
  });

  it("unpatches all on reset", () => {
    const fake = new FakeInstrumentor();
    _registerInstrumentor("fake", fake);
    autoInstrument();
    _resetInstrument();
    expect(fake.isPatched()).toBe(false);
  });

  it("_registerInstrumentor replaces existing instrumentor with same name", () => {
    const first = new FakeInstrumentor();
    const second = new FakeInstrumentor();
    _registerInstrumentor("dup", first);
    _registerInstrumentor("dup", second);
    autoInstrument();
    expect(first.isPatched()).toBe(false);
    expect(second.isPatched()).toBe(true);
  });

  it("accepts a Tracer argument without error", () => {
    const { Tracer } = require("../../src/core/tracer");
    const tracer = new Tracer();
    expect(() => autoInstrument(tracer)).not.toThrow();
  });
});
