# Frontend - Electron + React + TypeScript

## Scope
This directory contains the Electron desktop app with React UI.

## Key Rules
- contextIsolation=true, nodeIntegration=false, sandbox=true
- All IPC through contextBridge preload scripts
- All UI text in Turkish
- TypeScript strict mode, no `any`
- Functional React components with hooks

## Tech Stack
- electron-vite, React 18, TypeScript
- Tailwind CSS + shadcn/ui
- Zustand (client state), TanStack Query (server state)
- React Router DOM

## Running
```bash
cd apps/frontend
npm run dev
```

## Testing
```bash
cd apps/frontend
npm test
```

## Backend
Connects to FastAPI at http://127.0.0.1:8700
API spec: shared/api-spec.json
