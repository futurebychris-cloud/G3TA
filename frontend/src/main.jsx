import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { AccessibilityProvider } from './accessibility/AccessibilityContext.jsx'
import { TextToSpeechProvider } from './hooks/useTextToSpeech.js'
import './styles.css'
import './styles/accessibility.css'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AccessibilityProvider>
      <TextToSpeechProvider>
        <App />
      </TextToSpeechProvider>
    </AccessibilityProvider>
  </React.StrictMode>
)
