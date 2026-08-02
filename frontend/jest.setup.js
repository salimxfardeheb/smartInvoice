import "@testing-library/jest-dom";

// Polyfills jsdom pour les API navigateur utilisées par les composants.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

if (typeof window !== "undefined" && !window.URL.createObjectURL) {
  window.URL.createObjectURL = () => "blob:mock";
  window.URL.revokeObjectURL = () => {};
}

if (typeof globalThis.matchMedia === "undefined") {
  globalThis.matchMedia = () => ({
    matches: false,
    addListener: () => {},
    removeListener: () => {},
  });
}
