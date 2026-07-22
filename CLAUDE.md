# Project: Developer Platform

## Context
*   **WHAT:** A platform that evaluates the build stage of a developer's application and provides branched pathways to completion.
*   **WHY:** To automate project management, stage detection, and learning.

## Tech Stack
*   **Frontend:** Next.js (React)
*   **Backend:** Python (FastAPI)
*   **Database:** PostgreSQL
*   **AI Engine:** Google Gemini API

## UI/UX Design System
*   **Backgrounds:** Midnight Blue (`#191970`)
*   **Navigation & Cards:** Royal Purple (`#7851A9`) and Blue (`#0000FF`)
*   **Call-to-Action:** Ferrari Red (`#FF2800`)
*   **Borders & Accents:** Oak Brown (`#806517`)

## Core Features
*   **Project Management:** Options to start a new project from a template or upload an existing file tree/repo.
*   **Stage Evaluation:** Backend scripts scan the codebase for artifacts and dependencies, passing the tree to the Gemini API.
*   **Branching Pathways:** Display a visual, step-by-step branch of the next logical development actions.
*   **Learning Center:** Contextual markdown documentation dynamically loaded based on the current detected project stage.

## CORE BUSINESS RULES (CRITICAL)
*   **NO EXTRA CHARGES:** You must strictly utilize free APIs, permissive open-source libraries, and free-tier services. Do not implement any paid dependencies or services.
*   **EVERYTHING IS 100% MY PROPRIETARY:** All generated code, architecture, and logic belong strictly to the owner. Do not use copyleft licenses (e.g., GPL) that force open-sourcing.
