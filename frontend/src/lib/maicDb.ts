// lib/maicDb.ts — Client-side IndexedDB storage for MAIC classroom content

import Dexie, { type Table } from 'dexie';
import type { MAICSlide, MAICAgent, MAICOutlineScene, MAICChatMessage } from '../types/maic';
import type { MAICScene, SceneSlideBounds } from '../types/maic-scenes';

export interface StoredClassroom {
  id: string;
  title: string;
  slides: MAICSlide[];
  scenes: MAICScene[];
  outlines: MAICOutlineScene[];
  agents: MAICAgent[];
  chatHistory: MAICChatMessage[];
  audioCache: Record<string, ArrayBuffer>;
  config: Record<string, unknown>;
  /** Maps each scene to its slide range in the flat slides[] array */
  sceneSlideBounds?: SceneSlideBounds[];
  syncedAt: number;
}

class MAICDatabase extends Dexie {
  classrooms!: Table<StoredClassroom, string>;

  constructor() {
    super('learnpuddle-maic');
    this.version(1).stores({
      classrooms: 'id, title, syncedAt',
    });
    // v2: adds scenes field (non-indexed, so no schema change needed — Dexie
    // stores all fields regardless, but bumping version signals the upgrade)
    this.version(2).stores({
      classrooms: 'id, title, syncedAt',
    }).upgrade((tx) => {
      return tx.table('classrooms').toCollection().modify((classroom) => {
        if (!classroom.scenes) {
          classroom.scenes = [];
        }
      });
    });

    // v3: adds sceneSlideBounds for multi-slide scene support
    // Non-indexed field — Dexie stores all fields regardless, but version bump
    // triggers the upgrade to backfill legacy 1:1 classrooms
    this.version(3).stores({
      classrooms: 'id, title, syncedAt',
    }).upgrade((tx) => {
      return tx.table('classrooms').toCollection().modify((classroom) => {
        if (!classroom.sceneSlideBounds) {
          // Backward compat: legacy classrooms have 1 slide per scene
          classroom.sceneSlideBounds = (classroom.scenes || []).map((_: unknown, i: number) => ({
            sceneIdx: i,
            startSlide: i,
            endSlide: i,
          }));
        }
      });
    });
  }
}

export const maicDb = new MAICDatabase();

// ─── CRUD Helpers ─────────────────────────────────────────────────────────

export async function getStoredClassroom(id: string): Promise<StoredClassroom | undefined> {
  return maicDb.classrooms.get(id);
}

export async function saveClassroom(classroom: StoredClassroom): Promise<void> {
  await maicDb.classrooms.put({ ...classroom, syncedAt: Date.now() });
}

export async function updateClassroomSlides(id: string, slides: MAICSlide[]): Promise<void> {
  await maicDb.classrooms.update(id, { slides, syncedAt: Date.now() });
}

export async function updateClassroomScenes(id: string, scenes: MAICScene[]): Promise<void> {
  await maicDb.classrooms.update(id, { scenes, syncedAt: Date.now() });
}

export async function updateClassroomChat(id: string, chatHistory: MAICChatMessage[]): Promise<void> {
  await maicDb.classrooms.update(id, { chatHistory, syncedAt: Date.now() });
}

export async function cacheAudio(classroomId: string, sceneId: string, audio: ArrayBuffer): Promise<void> {
  const classroom = await maicDb.classrooms.get(classroomId);
  if (classroom) {
    const cache = { ...classroom.audioCache, [sceneId]: audio };
    await maicDb.classrooms.update(classroomId, { audioCache: cache });
  }
}

export async function deleteStoredClassroom(id: string): Promise<void> {
  await maicDb.classrooms.delete(id);
}

export async function listStoredClassrooms(): Promise<StoredClassroom[]> {
  return maicDb.classrooms.orderBy('syncedAt').reverse().toArray();
}
