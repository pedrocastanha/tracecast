const dir = new URL(".", import.meta.url).pathname;
export const MOUNT_PREFIX = dir.replace(/\/assets\/$/, "").replace(/\/$/, "");
export const API_BASE = `${MOUNT_PREFIX}/api`;
