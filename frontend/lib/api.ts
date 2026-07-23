export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TOKEN_KEY = "dp_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getToken();
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
}

export interface Project {
  id: number;
  name: string;
  description: string;
  source_type: string;
  template: string;
  stage: string;
  created_at: string;
}

export interface PathwayStep {
  title: string;
  detail: string;
}

export interface PathwayBranch {
  title: string;
  description: string;
  priority: "critical" | "recommended" | "optional";
  steps: PathwayStep[];
}

export interface Evaluation {
  id: number;
  stage: string;
  confidence: number;
  summary: string;
  engine: string;
  created_at: string;
  branches: PathwayBranch[];
  chosen_branch: number;
  completed_steps: number[];
  changes: string[];
}

export interface ProjectDetail extends Project {
  latest_evaluation: Evaluation | null;
}

export interface ScanSignals {
  has_readme: boolean;
  has_tests: boolean;
  has_ci: boolean;
  has_docker: boolean;
  has_lockfile: boolean;
  has_env_example: boolean;
  has_license: boolean;
  dependency_files: string[];
  dependencies: string[];
  languages: string[];
  file_count: number;
}

export interface ProjectTree {
  tree: string;
  signals: ScanSignals;
}

export interface Stats {
  total_projects: number;
  total_evaluations: number;
  steps_completed: number;
  stage_counts: Record<string, number>;
  gemini_evaluations: number;
}

export interface LearningContent {
  stage: string;
  markdown: string;
  stacks: string[];
}

export interface QuizQuestion {
  q: string;
  options: string[];
}

export interface QuizOut {
  stage: string;
  questions: QuizQuestion[];
}

export interface QuizReviewItem {
  q: string;
  correct: number;
  your: number;
  why: string;
}

export interface QuizResult {
  score: number;
  total: number;
  passed: boolean;
  review: QuizReviewItem[];
}

export interface CoachResult {
  markdown: string;
  engine: string;
}

export interface AuthResult {
  token: string;
  username: string;
}

export interface MeResult {
  username: string;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    if (res.status === 401) clearToken();
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  listProjects: () =>
    fetch(`${API_BASE}/api/projects`, { headers: authHeaders() }).then((r) =>
      handle<Project[]>(r)
    ),

  createProject: (payload: { name: string; description: string; template: string }) =>
    fetch(`${API_BASE}/api/projects`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    }).then((r) => handle<Project>(r)),

  uploadProject: (file: File, name: string) => {
    const form = new FormData();
    form.append("file", file);
    const params = name ? `?name=${encodeURIComponent(name)}` : "";
    return fetch(`${API_BASE}/api/projects/upload${params}`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    }).then((r) => handle<Project>(r));
  },

  importProject: (url: string, name: string) =>
    fetch(`${API_BASE}/api/projects/import`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ url, name }),
    }).then((r) => handle<Project>(r)),

  getProject: (id: string | number) =>
    fetch(`${API_BASE}/api/projects/${id}`, { headers: authHeaders() }).then((r) =>
      handle<ProjectDetail>(r)
    ),

  evaluateProject: (id: string | number) =>
    fetch(`${API_BASE}/api/projects/${id}/evaluate`, {
      method: "POST",
      headers: authHeaders(),
    }).then((r) => handle<Evaluation>(r)),

  reuploadProject: (id: string | number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API_BASE}/api/projects/${id}/reupload`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    }).then((r) => handle<Project>(r));
  },

  choosePathway: (id: string | number, branchIndex: number) =>
    fetch(`${API_BASE}/api/projects/${id}/pathway`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ branch_index: branchIndex }),
    }).then((r) => handle<Evaluation>(r)),

  updateStep: (id: string | number, stepIndex: number, done: boolean) =>
    fetch(`${API_BASE}/api/projects/${id}/pathway/steps`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ step_index: stepIndex, done }),
    }).then((r) => handle<Evaluation>(r)),

  coachStep: (id: string | number, branchIndex: number, stepIndex: number) =>
    fetch(`${API_BASE}/api/projects/${id}/coach`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ branch_index: branchIndex, step_index: stepIndex }),
    }).then((r) => handle<CoachResult>(r)),

  deleteProject: (id: string | number) =>
    fetch(`${API_BASE}/api/projects/${id}`, {
      method: "DELETE",
      headers: authHeaders(),
    }).then((r) => handle<void>(r)),

  getLearning: (stage: string, stack?: string) =>
    fetch(
      `${API_BASE}/api/learning/${stage}${stack ? `?stack=${encodeURIComponent(stack)}` : ""}`
    ).then((r) => handle<LearningContent>(r)),

  listEvaluations: (id: string | number) =>
    fetch(`${API_BASE}/api/projects/${id}/evaluations`, { headers: authHeaders() }).then((r) =>
      handle<Evaluation[]>(r)
    ),

  getProjectTree: (id: string | number) =>
    fetch(`${API_BASE}/api/projects/${id}/tree`, { headers: authHeaders() }).then((r) =>
      handle<ProjectTree>(r)
    ),

  getStats: () =>
    fetch(`${API_BASE}/api/stats`, { headers: authHeaders() }).then((r) => handle<Stats>(r)),

  getQuiz: (stage: string) =>
    fetch(`${API_BASE}/api/learning/${stage}/quiz`).then((r) => handle<QuizOut>(r)),

  submitQuiz: (stage: string, answers: number[]) =>
    fetch(`${API_BASE}/api/learning/${stage}/quiz`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    }).then((r) => handle<QuizResult>(r)),

  register: (username: string, password: string) =>
    fetch(`${API_BASE}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }).then((r) => handle<AuthResult>(r)),

  login: (username: string, password: string) =>
    fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }).then((r) => handle<AuthResult>(r)),

  logout: () =>
    fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      headers: authHeaders(),
    }).then((r) => handle<void>(r)),

  me: () =>
    fetch(`${API_BASE}/api/auth/me`, { headers: authHeaders() }).then((r) => handle<MeResult>(r)),
};
