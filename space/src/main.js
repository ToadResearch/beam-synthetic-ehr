import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'

// Focus rings are for the keyboard. A click or tap never leaves one behind, the Tab key brings them back.
const root = document.documentElement
addEventListener('pointerdown', () => (root.dataset.input = 'pointer'), true)
addEventListener('keydown', (e) => { if (e.key === 'Tab') root.dataset.input = 'keyboard' }, true)

mount(App, { target: document.getElementById('app') })
