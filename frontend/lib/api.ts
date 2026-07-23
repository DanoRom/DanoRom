export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
}

export interface ProjectDetail extends Project {
  latest_evaluation: Evaluation | null;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
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
    fetch(`${API_BASE}/api/projects`).then((r) => handle<Project[]>(r)),

  createProject: (payload: { name: string; description: string; template: string }) =>
    fetch(`${API_BASE}/api/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => handle<Project>(r)),

  uploadProject: (file: File, name: string) => {
    const form = new FormData();
    form.append("file", file);
    const params = name ? `?name=${encodeURIComponent(name)}` : "";
    return fetch(`${API_BASE}/api/projects/upload${params}`, {
      method: "POST",
      body: form,
    }).then((r) => handle<Project>(r));
  },

  getProject: (id: string | number) =>
    fetch(`${API_BASE}/api/projects/${id}`).then((r) => handle<ProjectDetail>(r)),

  evaluateProject: (id: string | number) =>
    fetch(`${API_BASE}/api/projects/${id}/evaluate`, { method: "POST" }).then((r) =>
      handle<Evaluation>(r)
    ),

  reuploadProject: (id: string | number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API_BASE}/api/projects/${id}/reupload`, {
      method: "POST",
      body: form,
    }).then((r) => handle<Project>(r));
  },

  choosePathway: (id: string | number, branchIndex: number) =>
    fetch(`${API_BASE}/api/projects/${id}/pathway`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ branch_index: branchIndex }),
    }).then((r) => handle<Evaluation>(r)),

  updateStep: (id: string | number, stepIndex: number, done: boolean) =>
    fetch(`${API_BASE}/api/projects/${id}/pathway/steps`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ step_index: stepIndex, done }),
    }).then((r) => handle<Evaluation>(r)),

  getLearning: (stage: string) =>
    fetch(`${API_BASE}/api/learning/${stage}`).then((r) =>
      handle<{ stage: string; markdown: string }>(r)
    ),
};
