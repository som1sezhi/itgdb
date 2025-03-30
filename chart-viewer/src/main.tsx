import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
// @ts-expect-error included by recommendation of https://vite.dev/guide/backend-integration.html
import 'vite/modulepreload-polyfill';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
