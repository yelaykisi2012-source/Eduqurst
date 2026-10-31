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
  is_admin: boolean;
}

/** Admin dashboard data: one grade with its subjects. */
export interface GradeOverview {
  grade_id: number;
  grade_name: string;
  subjects: AdminSubject[];
}

export interface AdminSubject {
  id: number;
  name: string;
  slug: string;
  emoji: string;
  grade_id: number;
  lesson_count: number;
  is_published: boolean;
}

export interface AdminLesson {
  id: number;
  title: string;
  level_order: number;
  subject_name: string;
  question_count: number;
  material_count: number;
  explanation: string;
  stars_reward: number;
  pass_threshold_percent: number;
  is_published: boolean;
}

/** Full admin view of a question, including which option is correct. */
export interface AdminQuestionOption {
  id: number;
  text: string;
  is_correct: boolean;
}

export interface AdminQuestionDetail {
  id: number;
  text: string;
  kind: string;
  option_count: number;
  correct_count: number;
  options: AdminQuestionOption[];
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

/** Full lesson payload from GET /api/lessons/{id} (pupil view). */
export interface LessonDetail {
  id: number;
  subject_name: string;
  title: string;
  explanation: string;
  video_url: string | null;
  level_order: number;
  stars_reward: number;
  pass_threshold_percent: number;
  materials: Material[];
  viewed: boolean;
  passed: boolean;
}

/** Payload the Telegram Login Widget hands to onTelegramAuth (browser login). */
export interface TelegramWebUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

/**
 * Lesson material. `kind` is one of:
 *   video | pdf  → content is an external URL OR an uploaded Telegram file
 *                  (file_id set; fetch bytes from /api/materials/{id}/file)
 *   live         → content is an external URL (Zoom/Meet/YouTube Live)
 *   text         → content is written explanation
 *   image | slide → legacy formats (image URL / slide text)
 */
export interface Material {
  id: number;
  kind: string;
  title: string;
  content: string;
  order_index: number;
  file_id: string | null;
  file_name: string | null;
  file_size: number | null;
}

/** Payload for POST /api/admin/lessons/{id}/materials. */
export interface MaterialCreate {
  kind: string;
  title: string;
  content: string;
  file_id?: string | null;
  file_name?: string | null;
  file_size?: number | null;
}

/** Quiz fetched from GET /api/lessons/{id}/quiz — never contains answers. */
export interface Quiz {
  lesson_id: number;
  lesson_title: string;
  pass_threshold_percent: number;
  questions: QuizQuestion[];
}

export interface QuizQuestion {
  id: number;
  text: string;
  kind: string; // single | text | image
  image_url: string | null;
  options: QuizOption[];
}

export interface QuizOption {
  id: number;
  text: string;
}

/** Result of POST /api/lessons/{id}/quiz/submit (graded on the server). */
export interface QuizResult {
  attempt_id: number;
  total_count: number;
  correct_count: number;
  score_percent: number;
  passed: boolean;
  stars_earned: number;
  stars_total: number;
  next_level_unlocked: boolean;
  message_uz: string;
  new_achievements: string[];
  new_achievement_titles: string[];
  duplicate: boolean;
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
