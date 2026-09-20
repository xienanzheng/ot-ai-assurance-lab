import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
export default defineConfig({plugins:[react()],publicDir:false,build:{outDir:'dist-home',rollupOptions:{input:fileURLToPath(new URL('./home.html',import.meta.url))}},server:{host:'127.0.0.1',port:18774,strictPort:true}});
