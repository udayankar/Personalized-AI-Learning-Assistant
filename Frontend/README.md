# Personalized AI Learning Assistant — Frontend

A modern, academic study workspace built with React, Redux Toolkit, and Parcel, connecting to a FastAPI backend powered by Retrieval-Augmented Generation (RAG) and Google Gemini.

---

## 🎨 Design System: 60–30–10 Academic Aesthetic

The user interface follows a focused, distraction-free academic workspace design:

* **60% — Soft Cream (`#fdfbf7`)**: Main page backgrounds, study workspace surfaces, cards, and content areas.
* **30% — Academic Navy (`#1a365d`)**: Navigation bar, sidebar, typography headers, primary body text, and structural interface elements.
* **10% — Academic Amber (`#d97706` / `#b45309`)**: Primary calls to action, active tab indicators, citation badges, progress bars, and status highlights.

All design tokens are centralized in `src/styles/variables.css` and applied using CSS Modules and pure CSS custom properties.

---

## 🛠️ Technology Stack

* **React 18** (JSX)
* **Parcel** (Bundler — zero config, fast HMR)
* **React Router v6** (Client-side routing with public and protected layouts)
* **Redux Toolkit & React Redux** (Global state management for auth, chat, documents, and UI notifications)
* **Axios** (Centralized API client with `withCredentials: true` for HttpOnly cookie session management)
* **Lucide React** (Consistent academic icon set)
* **React Markdown & Remark GFM** (Rendering AI study responses with code blocks, tables, and lists)
* **CSS Modules & CSS Variables** (Scoped component styling with design token consistency)

---

## 📁 Directory Structure

```text
Frontend/
├── .env.development                  # Dev backend configuration (http://localhost:8000)
├── .env.example                      # Template environment variables
├── .gitignore                        # Build artifacts and secrets exclusion
├── package.json                      # Scripts and dependencies
├── README.md                         # This documentation
└── src/
    ├── index.html                    # Parcel HTML entrypoint with academic typography
    ├── index.jsx                     # Root application bootstrap & Provider mount
    │
    ├── styles/                       # Design tokens and global stylesheets
    │   ├── variables.css             # 60-30-10 color palette & layout variables
    │   ├── reset.css                 # Modern CSS reset
    │   ├── typography.css            # Academic typography scale (Lora + Inter + Mono)
    │   └── global.css                # Global utilities and animations
    │
    ├── services/                     # HTTP communication layer
    │   ├── apiClient.js              # Centralized Axios instance with error normalization
    │   ├── authService.js            # /users/* authentication API calls
    │   ├── chatService.js            # /chat/query RAG query API calls
    │   └── documentService.js        # /documents/upload multipart upload calls
    │
    ├── store/                        # Redux store architecture
    │   ├── index.js                  # Combined store with logout cleanup middleware
    │   └── slices/
    │       ├── authSlice.js          # User profile, session check, login/signup/logout
    │       ├── chatSlice.js          # Active session messages, sources, retry logic
    │       ├── documentSlice.js      # PDF upload progress & session document tracker
    │       └── uiSlice.js            # Toast notifications & sidebar collapse state
    │
    ├── routes/                       # Routing configuration & guards
    │   ├── AppRoutes.jsx             # Route definitions
    │   ├── ProtectedRoute.jsx        # Auth guard redirecting to /login
    │   └── PublicOnlyRoute.jsx       # Guard redirecting signed-in users to /app
    │
    ├── layouts/                      # Layout shells
    │   ├── PublicLayout/             # Navigation and footer for public views
    │   └── AppLayout/                # Navy sidebar, header, and workspace container
    │
    ├── components/                   # Reusable UI components
    │   ├── Alert/                    # Error, warning, success banners
    │   ├── Badge/                    # Citation and status tags
    │   ├── Button/                   # Primary Amber, secondary Navy, outline buttons
    │   ├── Card/                     # Surface containers with consistent padding
    │   ├── EmptyState/               # Friendly empty state illustrations
    │   ├── ErrorBoundary/            # Global React error boundary
    │   ├── LoadingScreen/            # Session restoration loading view
    │   ├── TextInput/                # Accessible labeled input with error states
    │   └── Toast/                    # Stacked toast notification system
    │
    └── features/                     # Feature pages and workspaces
        ├── landing/                  # Public product introduction & workflow
        ├── auth/                     # Login & Signup forms with validation
        ├── dashboard/                # Academic dashboard & quick study actions
        ├── chat/                     # AI Learning Workspace & citation inspector
        ├── documents/                # Drag-and-drop PDF upload & RAG indexing monitor
        ├── settings/                 # Account information & system diagnostics
        └── notfound/                 # 404 handler
```

---

## 🚀 Getting Started

### 1. Prerequisites

* **Node.js**: v18.0.0 or higher (v24+ recommended)
* **npm**: v9.0.0 or higher
* **Python**: v3.10+ for the backend

### 2. Install Dependencies

```bash
cd Frontend
npm install
```

### 3. Start the Development Server

```bash
npm run start
```

The frontend application will be available at: **`http://localhost:1234`**

### 4. Build for Production

```bash
npm run build
```

Production-ready bundles will be generated in the `dist/` directory.

---

## 🔌 Backend Integration & Endpoints

The frontend connects directly to the FastAPI backend running at `http://localhost:8000`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/users/signup` | Creates a new account (`Name`, `Email`, `Password`) |
| `POST` | `/users/login` | Validates credentials and sets `access_token` HttpOnly cookie |
| `GET` | `/users/me` | Retrieves the authenticated user profile (`ID`, `Name`, `Email`, `Created_at`) |
| `POST` | `/users/logout` | Clears the `access_token` session cookie |
| `POST` | `/chat/query` | Submits a question and receives AI response with source document citations |
| `POST` | `/documents/upload` | Multipart upload (`file`) that triggers server FAISS re-indexing |

---

## 🔒 Security Architecture

1. **HttpOnly Cookies**: Authentication relies entirely on `HttpOnly` cookies. The frontend never accesses or stores JWT tokens in `localStorage`, `sessionStorage`, or Redux.
2. **Centralized Error Normalization**: FastAPI validation errors (`detail: [{loc, msg}]`) are normalized into clean, user-facing sentences without exposing backend traces.
3. **CORS Configuration**: The backend explicitly authorizes `http://localhost:1234` with `allow_credentials=True`.
