# Frontend

> ⚠️ **Important**: This directory is tracked in git but **not** in `.gitignore`.

## Dependencies

Runtime dependencies live in `package.json`:

- `react` `react-dom` — UI framework
- `react-router-dom` — Routing
- `lucide-react` — Icon set
- `vite` — Build tool
- `tailwindcss` — Utility-first CSS
- `typescript` — Type system

## Scripts

```bash
npm install          # Install dependencies
npm run dev          # Start dev server (HMR)
npm run build        # Build for production → dist/
npm run lint         # Run ESLint
npm run preview      # Preview production build
```

## Build output

After `npm run build`, the static bundle is emitted to `dist/`. The backend `serve` command serves this directory when present.