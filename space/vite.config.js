import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// Relative base so the built site works from any path, including a Hugging Face static Space.
export default defineConfig({ base: './', plugins: [svelte()] })
