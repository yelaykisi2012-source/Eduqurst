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
  /** Consecutive local (Asia/Tashkent) days with activity — shown as 🔥. */
  current_streak: number;
  max_streak: number;
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
  /** Only for kind="matching". */
  pairs: AdminPair[];
  /** True when this question belongs to the mandatory exam paper. */
  is_exam: boolean;
}

export interface AdminPair {
  left: string;
  right: string;
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
  kind: string; // single | text | image | matching
  image_url: string | null;
  options: QuizOption[];
  /** Left-hand items of a "matching" question (right choices are `options`). */
  prompts: MatchPrompt[];
}

export interface MatchPrompt {
  id: number;
  text: string;
}

export interface QuizOption {
  id: number;
  text: string;
}

/** Result of POST /api/lessons/{id}/quiz/submit (graded on the server). */
export interface Mistake {
  question_id: number;
  question_text: string;
  kind: string;
  your_answer: string;
  correct_answer: string;
  explanation: string;
}

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
  mistakes: Mistake[];
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

/** An issued course-completion certificate (GET /api/certificates). */
export interface Certificate {
  code: string;
  subject_id: number;
  subject_name: string;
  grade_name: string;
  pupil_name: string;
  score_percent: number;
  stars: number;
  issued_at: string;
  /** "course" (all lessons passed) | "exam" (mandatory exam passed). */
  issued_via: string;
  /** 5-point mark, set when issued_via === "exam": "5" | "4" | "2.5". */
  mark: string | null;
  /** Public QR verification page. */
  verify_url: string;
}

/** A finished course (GET /api/certificates/eligible); `certificate` set once issued. */
export interface EligibleCertificate {
  subject_id: number;
  subject_name: string;
  emoji: string;
  total_lessons: number;
  score_percent: number;
  certificate: Certificate | null;
}

/**
 * Mandatory subject exam (majburiy sertifikat).
 * GET /api/exams returns one card per published subject of the pupil's grade.
 */
export interface ExamCard {
  subject_id: number;
  subject_name: string;
  emoji: string;
  /** Questions in the paper — 0 while the admin has not flagged enough. */
  total: number;
  available: boolean;
  /** Set for 30 days after a failed sitting (ISO, UTC). */
  locked_until: string | null;
  best_score_percent: number | null;
  /** "5" | "4" | "2.5" of the best PASSED sitting. */
  best_mark: string | null;
  passed: boolean;
  certificate_code: string | null;
}

/** The frozen paper from GET /api/exams/{subjectId}/paper (no correct flags). */
export interface ExamPaper {
  attempt_id: number;
  subject_id: number;
  subject_name: string;
  total: number;
  pass_percent: number;
  lock_days: number;
  questions: QuizQuestion[];
}

/** Result of POST /api/exams/{subjectId}/submit. */
export interface ExamResult {
  attempt_id: number;
  total_count: number;
  correct_count: number;
  score_percent: number;
  mark: string;
  passed: boolean;
  stars_earned: number;
  stars_total: number;
  locked_until: string | null;
  certificate: Certificate | null;
  message_uz: string;
  mistakes: Mistake[];
}

/** Admin: how close a subject is to a ready 20-question paper. */
export interface AdminExamCoverage {
  subject_id: number;
  subject_name: string;
  grade_id: number;
  grade_name: string;
  flagged: number;
  ready: boolean;
  exam_size: number;
}

/** Weekly stars league (GET /api/leaderboard). */
export interface LeaderboardEntry {
  rank: number;
  user_id: number;
  first_name: string;
  stars: number;
  is_me: boolean;
}

export interface LeaderboardMe {
  rank: number;
  stars: number;
}

export interface Leaderboard {
  grade_id: number;
  grade_name: string;
  /** Local (Asia/Tashkent) Monday, ISO date. */
  week_start: string;
  /** Next Monday (exclusive), ISO date. */
  week_end: string;
  participants: number;
  top: LeaderboardEntry[];
  me: LeaderboardMe | null;
}
