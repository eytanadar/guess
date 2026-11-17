// The GUESS version: 2.<build date>, e.g. 2.20261117. The date is set by
// vite.config.ts when the page is built (or the dev server starts).
declare const __GUESS_BUILD__: string;

export const MAJOR = "2";
export const BUILD = typeof __GUESS_BUILD__ === "string" ? __GUESS_BUILD__ : "dev";
export const VERSION = `${MAJOR}.${BUILD}`;
