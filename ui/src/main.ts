import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: App },
    { path: '/rules', component: App },
    { path: '/watch/:source/:sourceId(.*)', component: App },
  ],
})

createApp(App).use(router).mount('#app')
