"use client";

import { useEffect, useState } from "react";
import { api, LearningContent, QuizOut, QuizResult } from "@/lib/api";
import Markdown from "@/components/Markdown";

const STACK_LABELS: Record<string, string> = {
  python: "Python",
  typescript: "TypeScript",
};

export default function LearningCenter({
  learning,
  onSelectStack,
}: {
  learning: LearningContent;
  onSelectStack: (stack?: string) => void;
}) {
  const [activeStack, setActiveStack] = useState("");

  // A new stage's content resets which stack toggle is highlighted.
  useEffect(() => {
    setActiveStack("");
  }, [learning.stage]);

  const selectStack = (stack: string) => {
    setActiveStack(stack);
    onSelectStack(stack || undefined);
  };

  return (
    <div className="learning">
      <span className="badge red">Learning Center</span>

      {learning.stacks.length > 0 && (
        <div className="stack-toggle-row">
          <button
            className={`stack-toggle ${activeStack === "" ? "active" : ""}`}
            onClick={() => selectStack("")}
          >
            General
          </button>
          {learning.stacks.map((stack) => (
            <button
              key={stack}
              className={`stack-toggle ${activeStack === stack ? "active" : ""}`}
              onClick={() => selectStack(stack)}
            >
              {STACK_LABELS[stack] ?? stack}
            </button>
          ))}
        </div>
      )}

      <Markdown source={learning.markdown} />

      <Quiz stage={learning.stage} />
    </div>
  );
}

function Quiz({ stage }: { stage: string }) {
  const [quiz, setQuiz] = useState<QuizOut | null>(null);
  const [answers, setAnswers] = useState<(number | null)[]>([]);
  const [result, setResult] = useState<QuizResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Loading a fresh stage's markdown invalidates any quiz in progress.
  useEffect(() => {
    setQuiz(null);
    setAnswers([]);
    setResult(null);
    setError("");
  }, [stage]);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.getQuiz(stage);
      setQuiz(data);
      setAnswers(new Array(data.questions.length).fill(null));
      setResult(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No quiz available for this stage yet");
    } finally {
      setLoading(false);
    }
  };

  const submit = async () => {
    if (!quiz) return;
    setSubmitting(true);
    setError("");
    try {
      setResult(await api.submitQuiz(stage, answers as number[]));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit quiz");
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    setQuiz(null);
    setAnswers([]);
    setResult(null);
    setError("");
  };

  if (!quiz) {
    return (
      <div className="quiz-box">
        <button className="ghost" onClick={load} disabled={loading}>
          {loading ? "Loading quiz…" : "Test your knowledge"}
        </button>
        {error && <p className="error">{error}</p>}
      </div>
    );
  }

  const allAnswered = answers.every((a) => a !== null);

  return (
    <div className="quiz-box">
      {!result && (
        <>
          {quiz.questions.map((q, qi) => (
            <div key={qi} className="quiz-question">
              <p>
                {qi + 1}. {q.q}
              </p>
              {q.options.map((option, oi) => (
                <label key={oi} className="quiz-option">
                  <input
                    type="radio"
                    name={`quiz-${qi}`}
                    checked={answers[qi] === oi}
                    onChange={() =>
                      setAnswers((prev) => prev.map((a, i) => (i === qi ? oi : a)))
                    }
                  />
                  <span>{option}</span>
                </label>
              ))}
            </div>
          ))}
          <button className="cta" onClick={submit} disabled={!allAnswered || submitting}>
            {submitting ? "Submitting…" : "Submit answers"}
          </button>
          {error && <p className="error">{error}</p>}
        </>
      )}

      {result && (
        <div>
          <div className="quiz-result-score">
            {result.score} / {result.total}
          </div>
          {result.passed && <span className="badge red">Stage mastered ✓</span>}

          {result.review.length > 0 && (
            <div style={{ marginTop: "1rem" }}>
              {result.review.map((item, i) => {
                const question = quiz.questions.find((qq) => qq.q === item.q);
                const correctText = question?.options[item.correct] ?? `Option ${item.correct + 1}`;
                const yourText = question?.options[item.your] ?? `Option ${item.your + 1}`;
                return (
                  <div key={i} className="quiz-review-item">
                    <div>
                      <strong>{item.q}</strong>
                    </div>
                    <div>Your answer: {yourText}</div>
                    <div className="correct">Correct answer: {correctText}</div>
                    <div className="why">{item.why}</div>
                  </div>
                );
              })}
            </div>
          )}

          <button className="ghost" onClick={reset} style={{ marginTop: "0.75rem" }}>
            Try again
          </button>
        </div>
      )}
    </div>
  );
}
