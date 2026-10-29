import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { LockGate } from './components/security/LockGate.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LockGate>
      <App />
    </LockGate>
  </StrictMode>,
)
