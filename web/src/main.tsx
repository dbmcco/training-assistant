import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

const THEME_STORAGE_KEY = 'training-assistant-theme'

function resolveInitialTheme(): 'light' | 'dark' {
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') {
    return stored
  }
  const hour = new Date().getHours()
  return hour >= 7 && hour < 18 ? 'light' : 'dark'
}

const initialTheme = resolveInitialTheme()
document.documentElement.setAttribute('data-theme', initialTheme)
document.documentElement.style.colorScheme = initialTheme

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
