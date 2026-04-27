// src/services/gradebookService.ts
//
// Admin gradebook aggregation — one row per teacher × course with quiz stats,
// assignment stats, and overall progress %. Thin API wrapper + client-side
// CSV export helper (no server round-trip).
//
// Backend: GET /api/v1/admin/gradebook/courses/{course_id}/
//          (apps/progress/assessment_views.py::course_gradebook)

import api from '../config/api';

export interface GradebookRow {
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  course_id: string;
  course_title: string;
  quiz_attempts: number;
  quiz_best_score_percent: number;
  quiz_passed: number;
  assignments_submitted: number;
  assignments_graded: number;
  assignments_avg_score: number;
  progress_percent: number;
}

/** Same shape the DataTable filters work against. */
export type GradebookStatusFilter =
  | 'all'
  | 'passed'
  | 'failed'
  | 'not_attempted';

export interface GradebookQuery {
  statusFilter?: GradebookStatusFilter;
  minScorePercent?: number;
  maxScorePercent?: number;
}

export const gradebookService = {
  /** Fetch per-teacher gradebook for a given course. */
  async getCourseGradebook(
    courseId: string,
  ): Promise<{ results: GradebookRow[] }> {
    const res = await api.get(`/admin/gradebook/courses/${courseId}/`);
    return res.data;
  },

  /** Apply status + score-range filters client-side. */
  applyFilters(rows: GradebookRow[], q: GradebookQuery): GradebookRow[] {
    const status = q.statusFilter ?? 'all';
    const min = q.minScorePercent ?? 0;
    const max = q.maxScorePercent ?? 100;

    return rows.filter((r) => {
      const pct = Number(r.quiz_best_score_percent) || 0;

      if (status === 'passed' && r.quiz_passed < 1) return false;
      if (status === 'failed' && !(r.quiz_attempts > 0 && r.quiz_passed === 0)) {
        return false;
      }
      if (status === 'not_attempted' && r.quiz_attempts > 0) return false;

      if (pct < min || pct > max) return false;
      return true;
    });
  },

  /** Serialize one row to a CSV-friendly object. */
  toCsvRow(row: GradebookRow): Record<string, string | number> {
    return {
      Teacher: row.teacher_name,
      Email: row.teacher_email,
      Course: row.course_title,
      'Quiz Attempts': row.quiz_attempts,
      'Best Score %': Number(row.quiz_best_score_percent).toFixed(1),
      'Quizzes Passed': row.quiz_passed,
      'Assignments Submitted': row.assignments_submitted,
      'Assignments Graded': row.assignments_graded,
      'Assignments Avg Score': Number(row.assignments_avg_score).toFixed(1),
      'Progress %': Number(row.progress_percent).toFixed(1),
    };
  },

  /**
   * Build a CSV string from an array of rows. The first row's keys become the
   * header. Values with commas/newlines/quotes are escaped per RFC 4180.
   */
  buildCsv(rows: Array<Record<string, string | number>>): string {
    if (rows.length === 0) return '';
    const headers = Object.keys(rows[0]);
    const escape = (v: string | number): string => {
      const s = String(v ?? '').replace(/"/g, '""');
      return /[",\n\r]/.test(s) ? `"${s}"` : s;
    };
    const lines: string[] = [];
    lines.push(headers.join(','));
    for (const row of rows) {
      lines.push(headers.map((h) => escape(row[h])).join(','));
    }
    return lines.join('\n');
  },

  /** Trigger a client-side CSV download (no server round-trip). */
  downloadCsv(rows: GradebookRow[], filename: string): void {
    if (rows.length === 0) return;
    const csvRows = rows.map((r) => this.toCsvRow(r));
    const csv = this.buildCsv(csvRows);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
};
