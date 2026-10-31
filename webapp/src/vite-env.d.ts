/// <reference types="vite/client" />

// Build-time env (public, baked into the bundle — NOT a secret).
// VITE_API_URL = base URL of the FastAPI backend, e.g. http://127.0.0.1:8000
interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Minimal typing for the Telegram Mini App SDK loaded via <script> in index.html.
// We only declare what the app actually uses; the rest comes in later stages.
interface TelegramWebAppUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
}

interface TelegramWebApp {
  ready: () => void;
  expand: () => void;
  // Raw signed initData string — the ONLY thing we trust for login, because
  // the backend verifies its HMAC signature. initDataUnsafe is for display only.
  initData: string;
  initDataUnsafe: { user?: TelegramWebAppUser };
  colorScheme: "light" | "dark";
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  HapticFeedback?: {
    impactOccurred: (style: string) => void;
    notificationOccurred: (type: string) => void;
    selectionChanged: () => void;
  };
}

interface TelegramLoginUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

interface Window {
  Telegram?: { WebApp: TelegramWebApp };
  // Global callback used by telegram-widget.js (data-onauth="onTelegramAuth(user)").
  onTelegramAuth?: (user: TelegramLoginUser) => void;
}

