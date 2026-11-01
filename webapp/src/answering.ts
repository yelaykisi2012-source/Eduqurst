/**
 * answering.ts — the single source of truth for "how a pupil answers a question".
 *
 * The lesson quiz (QuizPage) and the mandatory exam (ExamPage) show exactly the
 * same four question kinds, so the answering state and the payload the backend
 * expects (AnswerIn: option_id | text | pairs) live here once. A rule changed for
 * one format then applies to both screens automatically.
 */
import type { QuizQuestion } from "./types";

export interface AnswerState {
  /** question_id -> chosen option_id (single / image questions). */
  options: Record<number, number>;
  /** question_id -> typed answer (text questions). */
  texts: Record<number, string>;
  /** question_id -> prompt_id -> chosen option_id (matching questions). */
  matches: Record<number, Record<number, number>>;
}

export const EMPTY_STATE: AnswerState = { options: {}, texts: {}, matches: {} };

/** A question counts as answered only when it is fully answered. */
export function isAnswered(question: QuizQuestion, state: AnswerState): boolean {
  if (question.kind === "text") {
    return (state.texts[question.id] ?? "").trim().length > 0;
  }
  if (question.kind === "matching") {
    const assigned = state.matches[question.id] ?? {};
    return (
      question.prompts.length > 0 &&
      question.prompts.every((p) => assigned[p.id] !== undefined)
    );
  }
  return state.options[question.id] !== undefined;
}

export function answeredCount(questions: QuizQuestion[], state: AnswerState): number {
  return questions.filter((q) => isAnswered(q, state)).length;
}

/** One right-hand choice may serve a single prompt: reassigning moves it. */
export function withMatch(
  state: AnswerState,
  questionId: number,
  promptId: number,
  optionId: number | null,
): AnswerState {
  const forQuestion = { ...(state.matches[questionId] ?? {}) };
  if (optionId == null) {
    delete forQuestion[promptId];
  } else {
    for (const [pid, oid] of Object.entries(forQuestion)) {
      if (oid === optionId) delete forQuestion[Number(pid)];
    }
    forQuestion[promptId] = optionId;
  }
  return { ...state, matches: { ...state.matches, [questionId]: forQuestion } };
}

/**
 * The body `POST .../submit` expects: every question, in paper order.
 * Unanswered questions are still sent (a blank answer is simply marked wrong),
 * so the server count can never disagree with the paper.
 */
export function toPayload(questions: QuizQuestion[], state: AnswerState) {
  return questions.map((q) => {
    if (q.kind === "text") {
      return { question_id: q.id, text: (state.texts[q.id] ?? "").trim() };
    }
    if (q.kind === "matching") {
      const assigned = state.matches[q.id] ?? {};
      return {
        question_id: q.id,
        pairs: q.prompts.map((p) => ({
          prompt_id: p.id,
          option_id: assigned[p.id],
        })),
      };
    }
    return { question_id: q.id, option_id: state.options[q.id] };
  });
}
