// src/utils/generationLock.ts
//
// Module-level flag that MAIC generation hooks set while a classroom
// generation loop is running.  The session-lifecycle idle-timeout check
// reads this flag and skips logout when generation is in progress.

let _active = false;

export function setGenerationActive(active: boolean) {
  _active = active;
}

export function isGenerationActive(): boolean {
  return _active;
}
