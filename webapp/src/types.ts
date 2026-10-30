/**
 * types.ts — TypeScript shapes that mirror the backend Pydantic schemas.
 * Kept in one place so the API client and UI agree on the same contract.
 */

export interface Grade {
  id: number;
  name: string; // "1-sinf" .. "11-sinf"
  order_index: number;
}

export interface Profile {
  first_name: string;
  grade_id: number | null;
  grade_name: string | null;
  needs_grade_selection: boolean;
}

export interface LessonSummary {
  id: number;
  title: string;
  level_order: number;
  is_published: boolean;
  viewed: boolean;
  passed: boolean;
  unlocked: boolean;
}

export interface SubjectItem {
  id: number;
  name: string;
  slug: string;
  emoji: string;
  lessons: LessonSummary[];
}

export interface SubjectProgress {
  subject_name: string;
  emoji: string;
  total_lessons: number;
  passed_lessons: number;
}

export interface Achievement {
  code: string;
  title: string;
  description: string;
  icon: string;
  earned: boolean;
}

export interface Progress {
  first_name: string;
  grade_id: number | null;
  grade_name: string | null;
  stars_total: number;
  lessons_viewed: number;
  lessons_passed: number;
  subjects: SubjectProgress[];
  achievements: Achievement[];
}
