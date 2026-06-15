# Frontend

React 19 SPA, build bằng Vite, viết TypeScript.

## Tech Stack

| Thư viện | Vai trò |
|---|---|
| React 19 | UI framework |
| Vite 6 | Bundler / dev server |
| TypeScript 5 | Type safety |
| @supabase/supabase-js | Auth (login, session, JWT) |
| react-markdown + remark-gfm | Render markdown response |
| lucide-react | Icon library |

## Cấu trúc

```
frontend/src/
├── App.tsx                     # Root: AuthProvider → routing by auth status
├── main.tsx                    # ReactDOM entry
├── styles.css                  # Global CSS (~72KB, full design system)
│
├── app/
│   └── AppShell.tsx            # Layout sau login (sidebar + main)
│
├── features/
│   ├── auth/
│   │   ├── AuthContext.tsx      # Supabase auth state management
│   │   ├── LoginScreen.tsx      # Login UI (Supabase Auth)
│   │   └── InactiveScreen.tsx   # UI cho user bị inactive
│   ├── chat/
│   │   ├── ChatPanel.tsx        # Chat UI chính (send, receive, stream)
│   │   └── ConversationSidebar.tsx  # Sidebar danh sách conversations
│   ├── admin/
│   │   └── AdminDashboard.tsx   # Admin metrics + review queue
│   ├── settings/
│   │   └── SettingsScreen.tsx   # User preferences
│   └── knowledge/
│       └── (Knowledge browse UI)
│
├── components/
│   ├── ResponseRenderer.tsx    # Render response theo type (text/table/warning)
│   ├── FeedbackControls.tsx    # Thumbs up/down + reason selector
│   └── SourcePanel.tsx         # Hiển thị sources/citations
│
├── services/
│   ├── api.ts                  # API client (fetch wrapper + auth header)
│   └── supabase.ts             # Supabase client init
│
└── types/                      # TypeScript type definitions
```

## Auth Flow

```
App mount → AuthProvider
  → Supabase.auth.getSession()
    → loading: Spinner
    → no session: LoginScreen (Supabase Auth UI)
    → session exists:
        → GET /api/v1/me → check is_active
          → inactive: InactiveScreen
          → active: AppShell (chat, admin, settings)
```

Roles ảnh hưởng UI:
- `user`: Chat + Settings
- `reviewer`: + Message traces
- `admin`: + AdminDashboard, Review Queue

## Streaming

Chat hỗ trợ **SSE streaming** qua `POST /conversations/{id}/messages/stream`:
- Server gửi `event: stage`, `event: delta`, `event: sources`, `event: final`
- Frontend render token-by-token khi nhận `delta` events

## Development

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173
npm run build   # Production build → dist/
```
