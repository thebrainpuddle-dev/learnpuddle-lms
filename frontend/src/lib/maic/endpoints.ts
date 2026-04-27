// frontend/src/lib/maic/endpoints.ts
//
// Role-aware URL helpers for MAIC student + teacher endpoints.
// `MAICRole` is a structural alias for `MAICPlayerRole` in `types/maic.ts`.
// We duplicate it here (rather than re-export) to avoid a `lib/` -> `types/`
// import, which our convention keeps one-directional. The two MUST stay equal.
export type MAICRole = 'teacher' | 'student';

export function maicChatUrl(role: MAICRole): string {
  return `/api/v1/${role}/maic/chat/`;
}

export function maicTtsUrl(role: MAICRole): string {
  return `/api/v1/${role}/maic/generate/tts/`;
}

export function maicSceneActionsUrl(role: MAICRole): string {
  return `/api/v1/${role}/maic/generate/scene-actions/`;
}

export function maicQuizGradeUrl(role: MAICRole): string {
  return `/api/v1/${role}/maic/quiz-grade/`;
}

export function maicDirectorTurnUrl(role: MAICRole): string {
  return `/api/v1/${role}/maic/director/turn/`;
}

// Teacher-only: fire-and-forget progress ping during the generation
// wizard. Server stamps last_progress_at + phase/phase_scene_index/
// scenes_ready so MAICPlayerPage can render honest progress.
export function maicClassroomProgressUrl(classroomId: string): string {
  return `/api/v1/teacher/maic/classrooms/${classroomId}/progress/`;
}
