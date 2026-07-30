import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'sonner'
import App from './App'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
      <Toaster theme="light" position="bottom-right" closeButton richColors={false} duration={4000} toastOptions={{ className: 'neo-toast' }} />
    </BrowserRouter>
  </StrictMode>,
)
