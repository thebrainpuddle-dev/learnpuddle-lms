// Types for AI Study Summaries feature

export interface Flashcard {
  front: string;
  back: string;
}

export interface KeyTerm {
  term: string;
  definition: string;
}

export interface QuizQuestion {
  question: string;
  answer: string;
  type: 'mcq' | 'true_false' | 'fill_blank' | 'short_answer';
  options?: string[];
}

export interface MindMapNode {
  id: string;
  label: string;
  type: 'core' | 'concept' | 'process' | 'detail';
  description: string;
}

export interface MindMapEdge {
  source: string;
  target: string;
  label: string;
}

export interface MindMapData {
  nodes: MindMapNode[];
  edges: MindMapEdge[];
}

export interface StudySummaryData {
  summary: string;
  flashcards: Flashcard[];
  key_terms: KeyTerm[];
  quiz_prep: QuizQuestion[];
  mind_map?: MindMapData;
}

export interface StudySummaryListItem {
  id: string;
  content_id: string;
  content_title: string;
  content_type: string;
  course_title: string;
  course_id?: string;
  status: 'PENDING' | 'GENERATING' | 'READY' | 'FAILED';
  is_shared?: boolean;
  shared_by?: string;
  created_at: string;
  updated_at: string;
}

export interface StudySummaryDetail extends StudySummaryListItem {
  summary_data: StudySummaryData;
}
