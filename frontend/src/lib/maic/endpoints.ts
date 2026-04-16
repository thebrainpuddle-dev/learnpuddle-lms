// frontend/src/lib/maic/endpoints.ts
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
